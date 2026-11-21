"""GJ Academy Phase 1: local-only demonstration, never a broker integration."""
import os
import secrets
import time
import threading
import shark_exchange as shark
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory

app = Flask(__name__)
# Ephemeral by default: restarting rotates local browser sessions.
app.secret_key = os.environ.get('GJ_DEMO_SECRET', os.urandom(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict', MAX_CONTENT_LENGTH=16384, STATIC_EXPORT=False)
_previews = {}
_preview_lock = threading.Lock()

@app.before_request
def local_only():
    if request.remote_addr not in ('127.0.0.1', '::1') or request.host not in ('127.0.0.1:5000', 'localhost:5000', 'localhost', '127.0.0.1'):
        return 'Local access only', 403
    # Only navigations to local HTML pages establish a session. Sensitive POSTs
    # still require the same-origin and per-session CSRF checks below.
    if not app.config['STATIC_EXPORT'] and request.method == 'GET' and request.endpoint in ('login', 'page'):
        session.setdefault('student', 'Alex Morgan')
        session.setdefault('sid', secrets.token_urlsafe(32))
        session.setdefault('csrf', secrets.token_urlsafe(32))

@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    if request.path.startswith('/local/shark') or request.path in ('/subscribe', '/trading', '/dashboard'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.context_processor
def local_context():
    enabled = not app.config['STATIC_EXPORT']
    if enabled and session.get('student') and request.path in ('/subscribe','/trading','/dashboard'):
        session.setdefault('csrf', secrets.token_urlsafe(32))
    return {'local_features':enabled, 'csrf_token':session.get('csrf', '') if enabled else ''}



def protected(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('student'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


@app.route('/', methods=['GET', 'POST'])
def login():
    if not app.config['STATIC_EXPORT']:
        return redirect(url_for('page', name='dashboard'))
    if request.method == 'POST':
        if request.form.get('email', '').strip().lower() == 'student@gjacademy.com' and request.form.get('password') == 'Demo@123':
            session.clear()
            session['student'] = 'Alex Morgan'
            session['csrf'] = secrets.token_urlsafe(32)
            session['sid'] = secrets.token_urlsafe(32)
            session.permanent = bool(request.form.get('remember'))
            return redirect(url_for('page', name='strategies'))
        return render_template('login.html', error='Email or password does not match the demo account.'), 401
    if session.get('student'):
        return redirect(url_for('page', name='strategies'))
    return render_template('login.html')


@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/<name>')
@protected
def page(name):
    allowed = {'dashboard', 'strategies', 'strategy_details', 'subscribe', 'trading', 'orders', 'analytics', 'settings'}
    if name not in allowed:
        return 'Page not found', 404
    return render_template(name + '.html', page=name, student=session['student'])


def shark_guard(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        if app.config['STATIC_EXPORT'] or not session.get('student') or not session.get('sid'):
            return jsonify(error='Open the local dashboard first.'), 401
        if request.method != 'POST' or request.content_type != 'application/json':
            return jsonify(error='Invalid request.'), 403
        if request.headers.get('Origin') != 'http://' + request.host or request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin'):
            return jsonify(error='Local same-origin request required.'), 403
        supplied = request.headers.get('X-CSRF-Token', '')
        if not secrets.compare_digest(supplied, session.get('csrf', '')) or not supplied:
            return jsonify(error='Invalid session token.'), 403
        return fn(*args, **kwargs)
    return guarded

def live_config():
    header = os.environ.get('SHARK_DEVICE_HEADER_NAME', '')
    value = os.environ.get('SHARK_DEVICE_HEADER_VALUE', '')
    margin = os.environ.get('SHARK_MARGIN_ASSET', '')
    import re
    if os.environ.get('SHARK_LIVE_TRADING_ENABLED') == '1' and os.environ.get('SHARK_DEVICE_MODE') == 'DOCUMENTED_BODY' and re.fullmatch(r'[A-Z0-9]{2,12}', margin):
        return None, None, margin, 'DOCUMENTED_BODY'
    if os.environ.get('SHARK_LIVE_TRADING_ENABLED') != '1' or not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,63}', header) or header.lower() in ('api-key','signature','content-type','host','authorization') or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) or not re.fullmatch(r'[A-Z0-9]{2,12}', margin):
        return None
    return header, value, margin, 'HEADER'

@app.get('/local/shark-script.js')
@protected
def shark_script():
    if app.config['STATIC_EXPORT'] or not session.get('sid'):
        return 'Not available', 404
    return send_from_directory('local_only', 'shark-local.js', mimetype='application/javascript')

@app.post('/local/shark/status')
@shark_guard
def shark_status():
    try:
        creds = shark.load_credentials()
        # A hint is not evidence that the credentials are still valid.
        return jsonify(connected=bool(creds), hint=('••••' + creds['api_key'][-4:] if creds and len(creds['api_key']) > 4 else '••••'), enabled=bool(live_config()))
    except shark.SharkAPIError as exc:
        return jsonify(error=str(exc)), 503

@app.post('/local/shark/activity')
@shark_guard
def shark_activity():
    try:
        credentials = shark.load_credentials()
        if not credentials:
            return jsonify(error='Connect Shark on the subscription page to see account activity.'), 400
        return jsonify(shark.read_account_activity(credentials))
    except shark.SharkAPIError:
        return jsonify(error='Could not refresh Shark activity. Check your connection, API read permissions, and IP allowlisting.'), 503
    except Exception:
        return jsonify(error='Could not refresh Shark activity. Check Shark directly.'), 503

@app.post('/local/shark/connect')
@shark_guard
def shark_connect():
    data = request.get_json(silent=True) or {}
    if not isinstance(data,dict): return jsonify(error='Invalid request.'), 400
    key, secret = data.get('key'), data.get('secret')
    if not isinstance(key,str) or not isinstance(secret,str) or not key.strip() or not secret.strip() or len(key)>2048 or len(secret)>2048:
        return jsonify(error='Enter a valid key and secret.'), 400
    try:
        if not shark.keyring_backend_is_available():
            raise shark.SharkAPIError('A secure macOS Keychain backend is unavailable.')
        shark.test_connection(key, secret)
        shark.save_credentials(key, secret)
        return jsonify(message='Read-only verification succeeded. Credentials saved to macOS Keychain.')
    except shark.SharkAPIError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Connection could not be verified.'), 400

@app.post('/local/shark/disconnect')
@shark_guard
def shark_disconnect():
    try:
        shark.delete_credentials()
        with _preview_lock:
            _previews.pop(session['sid'], None)
        return jsonify(message='Keychain credentials removed.')
    except shark.SharkAPIError as exc:
        return jsonify(error=str(exc)), 503

@app.post('/local/shark/preview')
@shark_guard
def shark_preview():
    try:
        creds=shark.load_credentials()
        if not creds:
            raise shark.SharkAPIError('Connect Shark first.')
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict): raise ValueError('Invalid request.')
        order=shark.build_order_preview(data.get('side'),data.get('type'),data.get('quantity'),data.get('price'))
        config=live_config()
        if not config:
            raise shark.SharkAPIError('Live submission is disabled. Local trading configuration is required.')
        plan=shark.plan_order(creds,order,config[2])
        estimate=shark.market_estimate() if order['type'] == 'MARKET' else None
        token=secrets.token_urlsafe(32)
        with _preview_lock:
            _previews[session['sid']] = (token, order, time.monotonic()+120, config, plan)
        return jsonify(preview=plan['order'], intent=plan['intent'], position=plan['position'], market_estimate=estimate, token=token, enabled=True, margin_asset=config[2])
    except (ValueError, shark.SharkAPIError) as exc:
        return jsonify(error=str(exc)), 400

@app.post('/local/shark/submit')
@shark_guard
def shark_submit():
    config=live_config()
    if not config:
        return jsonify(error='Live submission is disabled. Local trading configuration is required.'), 403
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict): return jsonify(error='Invalid request.'), 400
    token=data.get('token')
    if data.get('confirmed') is not True:
        return jsonify(error='Explicit order confirmation is required.'), 400
    if not isinstance(token,str):
        return jsonify(error='A fresh order preview is required.'), 400
    with _preview_lock:
        record=_previews.pop(session['sid'], None)
        if not record or time.monotonic()>record[2] or not secrets.compare_digest(token,record[0]) or record[3] != config:
            return jsonify(error='Preview expired or was already used.'), 400
        order=record[1]
        submitted=False
        try:
            creds=shark.load_credentials()
            if not creds:
                raise shark.SharkAPIError('Connect Shark first.')
            shark.verify_metadata(order,config[2])
            current_plan=shark.plan_order(creds,order,config[2])
            if current_plan != record[4]:
                raise shark.SharkAPIError('The account position changed since the preview. Review a fresh order before proceeding.')
            payload={**current_plan['order'],'marginAsset':config[2]}
            if config[3] == 'DOCUMENTED_BODY':
                payload.update(deviceType='WEB', userCategory='EXTERNAL')
            headers={config[0]:config[1]} if config[0] else {}
            submitted=True
            result=shark._request('POST','/v1/order/place-order',creds['api_key'],creds['api_secret'],payload,extra_headers=headers)
            if not isinstance(result,dict):
                raise shark.SharkAPIError('Order response was unclear. Check Shark directly before retrying.')
            order_id=result.get('clientOrderId')
            if not isinstance(order_id,str) or len(order_id)>128:
                raise shark.SharkAPIError('Order response was unclear. Check Shark directly before retrying.')
            # Acceptance is not a fill. Reconcile read-only; failure remains unknown.
            import re
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', order_id):
                raise shark.SharkAPIError('Unrecognized order ID.')
            status='Accepted; fill status unconfirmed. Check Shark directly.'
            try:
                detail=shark._request('GET','/v1/order/'+order_id,creds['api_key'],creds['api_secret'])
                positions=shark._request('GET','/v1/positions/OPEN',creds['api_key'],creds['api_secret'],{'symbol':shark.SYMBOL,'pageSize':'20','sortOrder':'desc'})
                if isinstance(detail,dict) and detail.get('clientOrderId') == order_id and detail.get('status') in ('NEW','OPEN','FILLED','PARTIALLY_FILLED','CANCELLED','REJECTED','EXPIRED') and isinstance(positions,list):
                    status='Shark status: '+detail['status']+'. BTCUSDT position data retrieved; verify account details at Shark.'
            except shark.SharkAPIError:
                pass
            return jsonify(order_id=order_id,status=status)
        except shark.SharkAPIError as exc:
            if not submitted:
                return jsonify(error='Order not sent. '+str(exc)), 400
            message = str(exc) if getattr(exc, 'http_status', None) or getattr(exc, 'exchange_code', None) else 'Order outcome is unknown.'
            return jsonify(error=message+' Check Shark directly before retrying; no automatic retry was made.'), 400
        except Exception:
            return jsonify(error=('Order outcome is unknown. Check Shark directly before retrying.' if submitted else 'Order was not sent; the pre-order check failed.')), 400

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
