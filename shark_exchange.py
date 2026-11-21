"""Local Shark adapter. All network calls use the fixed production API origin."""
import hashlib
import hmac
import http.client
import socket
import json
import sys
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler

import keyring
from keyring.backends.macOS import Keyring as MacOSKeyring

SERVICE_NAME = 'GJInvestmentAcademy.SharkExchange'
KEYRING_ACCOUNT = 'local-account'
API_BASE = 'https://api.sharkexchange.in'
SYMBOL = 'BTCUSDT'
MINIMUM_QUANTITY = MAXIMUM_POC_QUANTITY = Decimal('0.002')

class SharkAPIError(Exception):
    def __init__(self, message, exchange_code=None, http_status=None):
        super().__init__(message)
        self.exchange_code = exchange_code
        self.http_status = http_status

# Only fixed, documented descriptions leave the backend; never echo exchange text.
_ORDER_ERRORS = {3000:'Incorrect device type reported by Shark.', 3001:'Symbol missing.', 3003:'Invalid leverage or unsupported order type.', 3004:'Invalid order side.', 3005:'Order price missing.', 3006:'Invalid quantity precision.', 3007:'Invalid price precision.', 3008:'Limit price missing.', 3009:'Limit price out of range.', 3010:'Quantity out of range.', 3012:'Margin asset not supported.', 3013:'An open order already exists.', 3014:'An open position already exists.', 3018:'Insufficient margin.', 3020:'API rate limit exceeded.', 3021:'Order type not supported.', 3029:'Order placement failed.'}

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def _ipv4_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Connect only over IPv4 so Shark sees the explicitly allowlisted IPv4."""
    host, port = address
    last_error = None
    for family, socktype, proto, _, sockaddr in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        sock = socket.socket(family, socktype, proto)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as error:
            last_error = error
            sock.close()
    raise last_error or OSError('No IPv4 address available.')

class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _ipv4_connection

class _IPv4HTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(_IPv4HTTPSConnection, request,
                            context=self._context, check_hostname=self._check_hostname)

# Direct IPv4 connection preserves the user's explicitly allowed outbound IP.
# Normal HTTPS certificate and hostname verification remain enabled.
_opener = build_opener(ProxyHandler({}), _NoRedirect(), _IPv4HTTPSHandler())

def keyring_backend_is_available(backend=None):
    try:
        backend = backend or keyring.get_keyring()
        return sys.platform == 'darwin' and type(backend) is MacOSKeyring and backend.priority > 0
    except Exception:
        return False

def _backend(backend=None):
    backend = backend or keyring.get_keyring()
    if not keyring_backend_is_available(backend):
        raise SharkAPIError('A secure macOS Keychain backend is unavailable.')
    return backend

def save_credentials(api_key, api_secret, backend=None):
    if not api_key or not api_secret:
        raise ValueError('Enter both the Shark API key and secret.')
    try:
        _backend(backend).set_password(SERVICE_NAME, KEYRING_ACCOUNT, json.dumps({'api_key':api_key,'api_secret':api_secret}))
    except SharkAPIError:
        raise
    except Exception:
        raise SharkAPIError('Could not save credentials to macOS Keychain.') from None

def load_credentials(backend=None):
    try:
        raw = _backend(backend).get_password(SERVICE_NAME, KEYRING_ACCOUNT)
        if not raw:
            return None
        value = json.loads(raw)
        if not isinstance(value, dict) or not all(isinstance(value.get(x), str) and value[x] for x in ('api_key','api_secret')):
            raise ValueError()
        return value
    except SharkAPIError:
        raise
    except Exception:
        raise SharkAPIError('Could not read credentials from macOS Keychain.') from None

def delete_credentials(backend=None):
    try:
        b = _backend(backend)
        if b.get_password(SERVICE_NAME, KEYRING_ACCOUNT):
            b.delete_password(SERVICE_NAME, KEYRING_ACCOUNT)
    except SharkAPIError:
        raise
    except Exception:
        raise SharkAPIError('Could not remove credentials from macOS Keychain.') from None

def _request(method, endpoint, api_key=None, api_secret=None, params=None, opener=None, extra_headers=None):
    if method not in ('GET','POST') or not endpoint.startswith('/v1/') or '?' in endpoint:
        raise SharkAPIError('Invalid exchange request.')
    params = dict(params or {})
    authenticated = api_key is not None and api_secret is not None
    if authenticated:
        params['timestamp'] = str(int(time.time() * 1000))
    query = urlencode(params) if method == 'GET' else ''
    data = json.dumps(params, separators=(',', ':'), allow_nan=False).encode() if method == 'POST' else None
    url = API_BASE + endpoint + ('?' + query if query else '')
    headers = {'User-Agent': 'GJ-Academy-Local-POC/1.0'}
    headers.update(extra_headers or {})
    if authenticated:
        signed = query.encode() if method == 'GET' else data
        headers.update({'api-key':api_key,'signature':hmac.new(api_secret.encode(),signed,hashlib.sha256).hexdigest()})
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with (opener or _opener.open)(req, timeout=10) as response:
            result = json.loads(response.read(2_000_001))
    except HTTPError as error:
        if endpoint == '/v1/order/place-order':
            # Shark uses several shapes, including {"error": "3000"}.
            # Never expose free-form exchange text, credentials or signatures.
            code = None
            try:
                body = json.loads(error.read(16384))
                if isinstance(body, dict):
                    for name in ('errorCode', 'code', 'error'):
                        value = body.get(name)
                        candidate = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
                        secrets_to_hide = (api_key or '', api_secret or '', headers.get('signature', ''))
                        if candidate.isascii() and candidate.isdigit() and 3 <= len(candidate) <= 5 and not any(candidate in item for item in secrets_to_hide if item):
                            code = int(candidate)
                            break
            except (TypeError, ValueError, OSError):
                pass
            message = 'Shark returned HTTP '+str(error.code)
            if code is not None:
                message += ' (code '+str(code)+')'
                if code in _ORDER_ERRORS:
                    message += ': '+_ORDER_ERRORS[code]
            else:
                message += '; no recognized error code was supplied.'
            raise SharkAPIError(message, exchange_code=code, http_status=error.code) from None
        if endpoint == '/v1/order/open-orders' and method == 'GET':
            # Only short numeric codes are shown, never arbitrary exchange text.
            # Exclude any string present in credentials or the generated signature.
            auth_code = None
            diagnostic = None
            try:
                raw = error.read(16384)
                if raw.strip().lower() == b'error code: 1010':
                    raise SharkAPIError('Shark edge service blocked the request (code 1010). Check network access or contact Shark support.')
                body = json.loads(raw)
                if isinstance(body, dict):
                    # Interpret only fixed categories; never send raw response text.
                    details = ' '.join(body.get(k, '') for k in ('message', 'details') if isinstance(body.get(k), str)).lower()
                    for sensitive in (api_key or '', api_secret or '', headers.get('signature', '')):
                        if sensitive:
                            details = details.replace(sensitive.lower(), '[redacted]')
                    categories = (
                        (('ip address', 'ip whitelist', 'ip whitelisting', 'ip allowlist', 'ip not allowed', 'ip restriction'), 'IP address restriction'),
                        (('signature',), 'request signature'),
                        (('api key', 'api-key', 'apikey'), 'API key'),
                        (('timestamp', 'clock skew'), 'request timestamp'),
                        (('permission', 'permissions'), 'API permissions'),
                        (('expired', 'expiration'), 'expired credential'),
                    )
                    diagnostic = next((label for phrases, label in categories if any(phrase in details for phrase in phrases)), None)
                    for name in ('errorCode', 'code', 'error'):
                        candidate = body.get(name)
                        candidate = str(candidate) if isinstance(candidate, (str, int)) and not isinstance(candidate, bool) else ''
                        secrets_to_hide = (api_key or '', api_secret or '', headers.get('signature', ''))
                        if candidate.isascii() and candidate.isdigit() and 3 <= len(candidate) <= 5 and not any(candidate in item for item in secrets_to_hide if item):
                            auth_code = ' (Shark code '+candidate+')'
                            break
            except (TypeError, ValueError, OSError):
                pass
            if error.code in (401, 403):
                raise SharkAPIError('Shark rejected authentication (HTTP '+str(error.code)+')'+(auth_code or '')+'.'+(' Shark response mentions '+diagnostic+'.' if diagnostic else '')+' Check the key, secret, account permissions and IP allowlisting.') from None
            if error.code in (400, 429, 500, 502, 503, 504):
                raise SharkAPIError('Shark returned HTTP '+str(error.code)+(auth_code or '')+' during the read-only connection test.'+(' Shark response mentions '+diagnostic+'.' if diagnostic else '')+' Please check the request or try again later.') from None
        raise SharkAPIError('Shark request failed. Check connectivity, permissions and IP allowlisting.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise SharkAPIError('Shark request failed or returned unreadable data. Check connectivity, permissions and IP allowlisting.') from None
    if not isinstance(result, (dict, list)) or isinstance(result, dict) and (result.get('error') or result.get('success') is False or result.get('errorCode')):
        raise SharkAPIError('Shark did not return a successful response.')
    return result

def test_connection(api_key, api_secret, opener=None):
    # The exchange's Python example uses only a signed timestamp for this check.
    result = _request('GET','/v1/order/open-orders',api_key,api_secret,opener=opener)
    if not isinstance(result, list) or not all(isinstance(x,dict) for x in result):
        raise SharkAPIError('Shark returned an unexpected open-orders response.')
    return result

def build_order_preview(side, order_type, quantity, price=None):
    side, order_type = str(side).upper(), str(order_type).upper()
    if side not in ('BUY','SELL') or order_type not in ('MARKET','LIMIT'):
        raise ValueError('Choose a valid side and order type.')
    try:
        q = Decimal(str(quantity))
        if not q.is_finite() or q != MAXIMUM_POC_QUANTITY:
            raise ValueError('Quantity must be exactly 0.002 BTC for this POC.')
        result = {'placeType':'ORDER_FORM','symbol':SYMBOL,'side':side,'type':order_type,'quantity':0.002,'reduceOnly':False}
        if order_type == 'LIMIT':
            p = Decimal(str(price))
            if not p.is_finite() or p <= 0 or p > Decimal('100000000'):
                raise ValueError('Enter a valid limit price.')
            result['price'] = float(p)
        return result
    except (InvalidOperation, TypeError):
        raise ValueError('Enter valid quantity and limit price.') from None

def market_estimate():
    data = _request('GET','/v1/market/ticker24Hr/BTCUSDT')
    try:
        ticker=data['data']
        price=Decimal(str(ticker['c']))
        age=abs(time.time()*1000 - int(ticker['E']))
        if ticker['s'] != SYMBOL or not price.is_finite() or price <= 0 or age > 120000:
            raise ValueError()
        return str(price)
    except (KeyError,TypeError,ValueError,InvalidOperation):
        raise SharkAPIError('A recent BTCUSDT market estimate is unavailable.') from None

def verify_metadata(payload, margin_asset):
    info = _request('GET','/v1/exchange/exchangeInfo',params={'market':'USDT'})
    if not isinstance(info, dict) or not isinstance(info.get('contracts'),list):
        raise SharkAPIError('Unable to verify Shark BTCUSDT contract metadata.')
    contract = next((x for x in info['contracts'] if isinstance(x,dict) and x.get('name') == SYMBOL),None)
    if not contract or margin_asset not in contract.get('marginAssetsSupported',[]) or payload['type'] not in contract.get('orderTypes',[]):
        raise SharkAPIError('BTCUSDT order type or configured margin asset could not be verified.')
    try:
        qp = int(contract['quantityPrecision']); pp = int(contract['pricePrecision'])
        filters = [x for x in contract['filters'] if x.get('filterType') == payload['type']+'_QTY_SIZE']
        if len(filters)!=1 or not 0 <= qp <= 12 or not 0 <= pp <= 12:
            raise ValueError()
        q=Decimal(str(payload['quantity'])); f=filters[0]
        if q < Decimal(str(f['minQty'])) or q > Decimal(str(f['maxQty'])) or q != q.quantize(Decimal(1).scaleb(-qp)):
            raise ValueError()
        if 'stepSize' in f and (q % Decimal(str(f['stepSize'])) != 0):
            raise ValueError()
        if 'price' in payload:
            p=Decimal(str(payload['price']))
            if p != p.quantize(Decimal(1).scaleb(-pp)):
                raise ValueError()
    except (KeyError,TypeError,ValueError,InvalidOperation,ZeroDivisionError):
        raise SharkAPIError('BTCUSDT quantity or price precision could not be verified against Shark metadata.') from None

def assert_flat(credentials):
    for endpoint in ('/v1/order/open-orders','/v1/positions/OPEN'):
        result = _request('GET',endpoint,credentials['api_key'],credentials['api_secret'],{'symbol':SYMBOL,'pageSize':'20','sortOrder':'desc'})
        # Only an explicit empty list is accepted; unknown pagination/envelopes fail closed.
        if not isinstance(result,list) or result:
            raise SharkAPIError('Cannot verify a flat BTCUSDT account, or an open order/position exists.')

def plan_order(credentials, order, margin_asset):
    """Determine whether an order opens a new position or reduces one specific position."""
    params={'symbol':SYMBOL,'pageSize':'20','sortOrder':'desc'}
    orders=_request('GET','/v1/order/open-orders',credentials['api_key'],credentials['api_secret'],params)
    positions=_request('GET','/v1/positions/OPEN',credentials['api_key'],credentials['api_secret'],params)
    if not isinstance(orders,list) or not isinstance(positions,list) or any(not isinstance(x,dict) for x in orders+positions):
        raise SharkAPIError('Cannot verify open BTCUSDT orders and positions. Check Shark directly.')
    if orders:
        raise SharkAPIError('An open BTCUSDT order exists. Manage it on Shark before placing another order.')
    if not positions:
        return {'order':dict(order), 'intent':'OPEN', 'position':None}
    if len(positions)!=1:
        raise SharkAPIError('Multiple BTCUSDT positions returned; manage them on Shark.')
    p=positions[0]
    import re
    position_id=p.get('positionId')
    direction=p.get('positionType')
    if (p.get('contractPair') != SYMBOL or direction not in ('LONG','SHORT')
        or p.get('positionStatus') != 'OPEN' or not isinstance(position_id,str)
        or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',position_id)
        or p.get('marginAsset') != margin_asset
        or p.get('baseAsset') != 'BTC' or p.get('quoteAsset') != 'USDT'):
        raise SharkAPIError('Cannot verify the open position, its margin asset, or its direction. Check Shark directly.')
    try:
        quantity=Decimal(str(p['quantity']))
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError()
        # Shark's live BTCUSDT response uses quantity for BTC and may report
        # positionAmount as quote-currency notional. Do not compare the units.
        if Decimal(str(order['quantity'])) > quantity:
            raise SharkAPIError('The requested quantity exceeds the open BTCUSDT position.')
    except (KeyError,TypeError,ValueError,InvalidOperation):
        raise SharkAPIError('Cannot verify the open position quantity. Check Shark directly.') from None
    expected_side='SELL' if direction=='LONG' else 'BUY'
    if order['side'] != expected_side:
        raise SharkAPIError('The selected side would increase the existing position. Manage it on Shark or select the opposite side to reduce it.')
    snapshot={'positionId':position_id,'direction':direction,'quantity':str(quantity),'marginAsset':margin_asset}
    reduced={**order,'placeType':'POSITION','positionId':position_id,'reduceOnly':True}
    return {'order':reduced, 'intent':'REDUCE', 'position':snapshot}

def read_account_activity(credentials):
    """Read recent BTCUSDT activity. Exchange records never enter demo state."""
    params = {'symbol': SYMBOL, 'pageSize': '20', 'sortOrder': 'desc'}
    sources = (
        ('orders', '/v1/order/open-orders', ('clientOrderId', 'symbol', 'side', 'type', 'orderAmount', 'filledAmount', 'price', 'time')),
        ('trades', '/v1/user-data/trade-history', ('id', 'clientOrderId', 'symbol', 'side', 'type', 'quantity', 'price', 'time')),
        ('positions', '/v1/positions/OPEN', ('positionId', 'contractPair', 'positionType', 'quantity', 'entryPrice', 'positionStatus', 'createdTime')),
        ('history', '/v1/order/order-history', ('clientOrderId', 'symbol', 'side', 'type', 'status', 'executedQty', 'price', 'updatedAt')),
    )
    activity = {}
    for name, endpoint, fields in sources:
        response = _request('GET', endpoint, credentials['api_key'], credentials['api_secret'], params)
        # Some installations wrap lists in a data field; unknown shapes are errors,
        # never evidence that the account has no activity.
        records = response.get('data') if isinstance(response, dict) else response
        if name == 'positions' and isinstance(response, dict) and response.get('contractPair'):
            records = [response]
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise SharkAPIError('Shark returned an unexpected activity response. Check Shark directly.')
        clean = []
        for record in records[:20]:
            symbol = record.get('symbol', record.get('contractPair'))
            if symbol != SYMBOL:
                continue
            clean.append({field: str(record[field])[:160] for field in fields
                          if field in record and isinstance(record[field], (str, int, float)) and not isinstance(record[field], bool)})
        activity[name] = clean
    return activity
