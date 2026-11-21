import hashlib
import hmac
import json
import unittest
import io
from urllib.error import HTTPError
from urllib.parse import urlparse
from unittest.mock import patch

import shark_exchange as shark
from app import app

class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, *args): return json.dumps(self.value).encode()

class FakeKeychain:
    def __init__(self): self.value = None
    def set_password(self, service, name, value): self.value = value
    def get_password(self, service, name): return self.value
    def delete_password(self, service, name): self.value = None

class SharkTests(unittest.TestCase):
    def test_signed_get_and_post_exact_bytes(self):
        captured=[]
        def opener(request, timeout): captured.append(request); return Response([])
        shark._request('GET','/v1/order/open-orders','key','secret',{'symbol':'BTCUSDT'},opener=opener)
        shark._request('POST','/v1/order/place-order','key','secret',{'quantity':0.002},opener=opener)
        for req in captured:
            payload=urlparse(req.full_url).query.encode() if req.method=='GET' else req.data
            self.assertEqual(req.get_header('Signature'),hmac.new(b'secret',payload,hashlib.sha256).hexdigest())
        self.assertIsNone(captured[0].data)
        self.assertEqual(captured[0].get_header('User-agent'),'GJ-Academy-Local-POC/1.0')

    def test_shark_network_connection_selects_only_ipv4(self):
        import socket
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('203.0.113.10',443))]
        with patch.object(shark.socket,'getaddrinfo',return_value=addresses) as resolve, patch.object(shark.socket,'socket') as factory:
            result=shark._ipv4_connection(('api.sharkexchange.in',443),10)
        resolve.assert_called_once_with('api.sharkexchange.in',443,socket.AF_INET,socket.SOCK_STREAM)
        factory.return_value.settimeout.assert_called_once_with(10)
        factory.return_value.connect.assert_called_once_with(('203.0.113.10',443))
        self.assertIs(result,factory.return_value)

    def test_known_exchange_error_is_sanitized(self):
        def opener(req, timeout):
            raise HTTPError(req.full_url,400,'failure',{},io.BytesIO(b'{"code":3000,"message":"private-secret-must-not-leak"}'))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark._request('POST','/v1/order/place-order','key','secret',{'side':'BUY'},opener=opener)
        self.assertEqual(error.exception.exchange_code,3000)
        self.assertIn('3000',str(error.exception))
        self.assertNotIn('private-secret',str(error.exception))

    def test_shark_order_error_field_and_unknown_code_are_safe(self):
        def make_opener(body, status):
            def opener(req, timeout):
                raise HTTPError(req.full_url,status,'failure',{},io.BytesIO(json.dumps(body).encode()))
            return opener
        for body,code in [({'error':'3000','details':'secret material'},3000),({'error':'4009','details':'secret material'},4009)]:
            with self.assertRaises(shark.SharkAPIError) as error:
                shark._request('POST','/v1/order/place-order','key','private',{'side':'BUY'},opener=make_opener(body,400))
            self.assertEqual(error.exception.exchange_code,code)
            self.assertEqual(error.exception.http_status,400)
            self.assertIn(str(code),str(error.exception))
            self.assertNotIn('secret material',str(error.exception))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark._request('POST','/v1/order/place-order','key','private',{'side':'BUY'},opener=make_opener({'message':'private'},503))
        self.assertIn('HTTP 503',str(error.exception))
        self.assertNotIn('private',str(error.exception))

    def test_authentication_error_reports_safe_status_without_exchange_text(self):
        def opener(req, timeout):
            raise HTTPError(req.full_url,403,'failure',{},io.BytesIO(b'{"error":"4002","details":"sensitive-value"}'))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark.test_connection('key','secret',opener=opener)
        self.assertIn('HTTP 403',str(error.exception))
        self.assertIn('4002',str(error.exception))
        self.assertNotIn('sensitive-value',str(error.exception))
        self.assertNotIn('secret',str(error.exception).replace('key, secret',''))

    def test_connection_request_uses_documented_timestamp_only(self):
        captured=[]
        def opener(request, timeout):
            captured.append(request)
            return Response([])
        shark.test_connection('key','secret',opener=opener)
        from urllib.parse import parse_qs
        self.assertEqual(set(parse_qs(urlparse(captured[0].full_url).query)), {'timestamp'})

    def test_bad_request_includes_safe_code_and_category(self):
        def opener(req, timeout):
            raise HTTPError(req.full_url,400,'failure',{},io.BytesIO(b'{"error":"4003","details":"invalid signature"}'))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark.test_connection('key','secret',opener=opener)
        self.assertIn('HTTP 400',str(error.exception))
        self.assertIn('4003',str(error.exception))
        self.assertIn('request signature',str(error.exception))

    def test_edge_block_is_distinguished_from_authentication(self):
        def opener(req, timeout):
            raise HTTPError(req.full_url,403,'failure',{},io.BytesIO(b'error code: 1010'))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark.test_connection('key','secret',opener=opener)
        self.assertIn('1010',str(error.exception))
        self.assertIn('edge service',str(error.exception))

    def test_connection_error_code_and_sensitive_body_handling(self):
        def make_opener(body):
            def opener(req, timeout):
                raise HTTPError(req.full_url,403,'failure',{},io.BytesIO(json.dumps(body).encode()))
            return opener
        with self.assertRaises(shark.SharkAPIError) as error:
            shark.test_connection('key','secret',opener=make_opener({'errorCode':4999,'details':'private detail'}))
        self.assertIn('4999',str(error.exception))
        self.assertNotIn('private detail',str(error.exception))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark.test_connection('key','secret-4999',opener=make_opener({'errorCode':4999}))
        self.assertNotIn('4999',str(error.exception))

    def test_connection_diagnostic_uses_only_fixed_safe_categories(self):
        def opener(req, timeout):
            body={'error':'4009','details':'Signature mismatch; private-content'}
            raise HTTPError(req.full_url,403,'failure',{},io.BytesIO(json.dumps(body).encode()))
        with self.assertRaises(shark.SharkAPIError) as error:
            shark.test_connection('key','secret',opener=opener)
        self.assertIn('request signature',str(error.exception))
        self.assertNotIn('private-content',str(error.exception))

    def test_secure_backend_and_keychain_lifecycle(self):
        b=FakeKeychain()
        self.assertFalse(shark.keyring_backend_is_available(b))
        with patch.object(shark,'keyring_backend_is_available',return_value=True):
            shark.save_credentials('key','secret',b)
            self.assertEqual(shark.load_credentials(b)['api_secret'],'secret')
            shark.delete_credentials(b)
            self.assertIsNone(shark.load_credentials(b))

    def test_preview_validation(self):
        for q in ('0.001','0.003','NaN','Infinity'):
            with self.assertRaises(ValueError): shark.build_order_preview('BUY','MARKET',q)
        p=shark.build_order_preview('SELL','LIMIT','0.002','63000')
        self.assertEqual(p['side'],'SELL'); self.assertEqual(p['price'],63000)
        self.assertNotIn('marginAsset',p)
        with self.assertRaises(ValueError): shark.build_order_preview('BUY','LIMIT','0.002')

    def test_connection_rejects_unexpected_response(self):
        with self.assertRaises(shark.SharkAPIError):
            shark.test_connection('k','s',opener=lambda *a,**kw:Response({'message':'bad'}))

    def test_metadata_requires_limits_precision_and_supported_margin(self):
        order=shark.build_order_preview('BUY','LIMIT','0.002','63000.1')
        metadata={'contracts':[{'name':'BTCUSDT','marginAssetsSupported':['INR'],'orderTypes':['LIMIT'],'quantityPrecision':3,'pricePrecision':1,'filters':[{'filterType':'LIMIT_QTY_SIZE','minQty':'0.002','maxQty':'1','stepSize':'0.001'}]}]}
        with patch.object(shark,'_request',return_value=metadata):
            shark.verify_metadata(order,'INR')
            with self.assertRaises(shark.SharkAPIError): shark.verify_metadata(order,'USDT')
            metadata['contracts'][0]['filters'][0]['minQty']='0.003'
            with self.assertRaises(shark.SharkAPIError): shark.verify_metadata(order,'INR')

    def test_activity_is_read_only_and_separates_orders_fills_and_positions(self):
        credentials={'api_key':'key','api_secret':'secret'}
        results=[
            [{'clientOrderId':'pending-1','symbol':'BTCUSDT','side':'BUY','orderAmount':'0.002','secret':'do-not-expose'}],
            [{'id':123,'symbol':'BTCUSDT','side':'BUY','price':'65000','quantity':'0.002'}, {'id':124,'symbol':'ETHUSDT','side':'BUY'}],
            {'contractPair':'BTCUSDT','positionType':'LONG','quantity':'0.002'},
            [{'clientOrderId':'past-1','symbol':'BTCUSDT','side':'SELL','status':'REJECTED'}],
        ]
        with patch.object(shark,'_request',side_effect=results) as request:
            data=shark.read_account_activity(credentials)
        self.assertEqual([call.args[0] for call in request.call_args_list],['GET','GET','GET','GET'])
        self.assertEqual(data['orders'][0]['clientOrderId'],'pending-1')
        self.assertNotIn('secret',data['orders'][0])
        self.assertEqual(len(data['trades']),1)
        self.assertEqual(data['trades'][0]['side'],'BUY')
        self.assertEqual(data['positions'][0]['positionType'],'LONG')
        self.assertEqual(data['history'][0]['status'],'REJECTED')
        self.assertNotIn('status',data['orders'][0])

    def test_activity_unexpected_response_is_error_not_empty(self):
        with patch.object(shark,'_request',return_value={'message':'unexpected'}):
            with self.assertRaises(shark.SharkAPIError):
                shark.read_account_activity({'api_key':'key','api_secret':'secret'})

    def test_position_order_intent_and_safety(self):
        creds={'api_key':'k','api_secret':'s'}
        buy=shark.build_order_preview('BUY','MARKET','0.002')
        sell=shark.build_order_preview('SELL','MARKET','0.002')
        long={'contractPair':'BTCUSDT','positionId':'pos-1','positionType':'LONG','positionStatus':'OPEN','quantity':'0.002','positionAmount':'126.214','baseAsset':'BTC','quoteAsset':'USDT','marginAsset':'INR'}
        with patch.object(shark,'_request',side_effect=[[],[]]):
            self.assertEqual(shark.plan_order(creds,sell,'INR')['intent'],'OPEN')
        with patch.object(shark,'_request',side_effect=[[],[long]]):
            plan=shark.plan_order(creds,sell,'INR')
        self.assertEqual(plan['intent'],'REDUCE')
        self.assertEqual(plan['order']['placeType'],'POSITION')
        self.assertEqual(plan['order']['positionId'],'pos-1')
        self.assertIs(plan['order']['reduceOnly'],True)
        with patch.object(shark,'_request',side_effect=[[],[long]]):
            with self.assertRaises(shark.SharkAPIError): shark.plan_order(creds,buy,'INR')
        with patch.object(shark,'_request',side_effect=[[{'symbol':'BTCUSDT'}],[long]]):
            with self.assertRaises(shark.SharkAPIError): shark.plan_order(creds,sell,'INR')
        with patch.object(shark,'_request',side_effect=[[],[{**long,'quantity':'0.001','positionAmount':'0.001'}]]):
            with self.assertRaises(shark.SharkAPIError): shark.plan_order(creds,sell,'INR')
        with patch.object(shark,'_request',side_effect=[[],[{**long,'marginAsset':'USDT'}]]):
            with self.assertRaises(shark.SharkAPIError): shark.plan_order(creds,sell,'INR')
        with patch.object(shark,'_request',side_effect=[[],[{**long,'baseAsset':'ETH'}]]):
            with self.assertRaises(shark.SharkAPIError): shark.plan_order(creds,sell,'INR')
        short={**long,'positionType':'SHORT','positionAmount':'126.214'}
        with patch.object(shark,'_request',side_effect=[[],[short]]):
            self.assertEqual(shark.plan_order(creds,buy,'INR')['intent'],'REDUCE')

    def test_flat_checks_fail_closed(self):
        with patch.object(shark,'_request',return_value={'data':[]}):
            with self.assertRaises(shark.SharkAPIError): shark.assert_flat({'api_key':'k','api_secret':'s'})
        with patch.object(shark,'_request',return_value=[{'symbol':'BTCUSDT'}]):
            with self.assertRaises(shark.SharkAPIError): shark.assert_flat({'api_key':'k','api_secret':'s'})

class LocalRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True,STATIC_EXPORT=False)
        self.c=app.test_client()
        self.c.get('/dashboard')
        with self.c.session_transaction() as session: self.csrf=session['csrf']
        self.headers={'Origin':'http://localhost','X-CSRF-Token':self.csrf}
    def post(self,path,data=None,headers=None):
        return self.c.post('/local/shark/'+path,json=data or {},headers=headers or self.headers)
    def test_guards(self):
        self.assertEqual(self.post('status',headers={'Origin':'http://evil.test','X-CSRF-Token':self.csrf}).status_code,403)
        self.assertEqual(self.post('status',headers={'Origin':'http://localhost','X-CSRF-Token':'bad'}).status_code,403)
        self.assertEqual(self.c.post('/local/shark/status',json={},headers=self.headers,environ_base={'REMOTE_ADDR':'192.0.2.1'}).status_code,403)
        self.assertEqual(self.c.post('/local/shark/status',json={},headers={**self.headers,'Host':'evil.test'}).status_code,403)
    def test_connect_verified_before_save_and_no_secrets_in_response(self):
        with patch.object(shark,'keyring_backend_is_available',return_value=True), patch.object(shark,'test_connection',return_value=[]), patch.object(shark,'save_credentials') as save:
            response=self.post('connect',{'key':'privatekey','secret':'privatesecret'})
            self.assertEqual(response.status_code,200);save.assert_called_once_with('privatekey','privatesecret')
            self.assertNotIn(b'privatekey',response.data);self.assertNotIn(b'privatesecret',response.data)
        with patch.object(shark,'keyring_backend_is_available',return_value=True), patch.object(shark,'test_connection',side_effect=shark.SharkAPIError('Rejected')), patch.object(shark,'save_credentials') as save:
            self.assertEqual(self.post('connect',{'key':'key','secret':'secret'}).status_code,400);save.assert_not_called()
    def test_activity_requires_credentials_and_preserves_csrf_guards(self):
        with patch.object(shark,'load_credentials',return_value=None):
            self.assertEqual(self.post('activity').status_code,400)
        with patch.object(shark,'load_credentials',return_value={'api_key':'key','api_secret':'secret'}), patch.object(shark,'read_account_activity',return_value={'orders':[],'trades':[{'id':'1','side':'BUY','symbol':'BTCUSDT'}],'positions':[]}):
            response=self.post('activity')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json()['trades'][0]['side'],'BUY')
            self.assertNotIn(b'secret',response.data)
        self.assertEqual(self.post('activity',headers={'Origin':'http://evil.test','X-CSRF-Token':self.csrf}).status_code,403)

    def test_live_preview_is_single_use_and_checks_are_required(self):
        env={'SHARK_LIVE_TRADING_ENABLED':'1','SHARK_DEVICE_HEADER_NAME':'X-Verified-Device','SHARK_DEVICE_HEADER_VALUE':'verified','SHARK_MARGIN_ASSET':'INR'}
        creds={'api_key':'privatekey','api_secret':'privatesecret'}
        with patch.dict('os.environ',env), patch.object(shark,'load_credentials',return_value=creds), patch.object(shark,'market_estimate',return_value='67000'), patch.object(shark,'verify_metadata') as metadata, patch.object(shark,'plan_order',side_effect=lambda creds,order,margin:{'order':dict(order),'intent':'OPEN','position':None}) as plan, patch.object(shark,'_request',side_effect=[{'clientOrderId':'order-1'}, {'clientOrderId':'order-1','status':'NEW'}, []]) as exchange:
            preview=self.post('preview',{'side':'BUY','type':'MARKET','quantity':'0.002'}).get_json()
            self.assertEqual(preview['market_estimate'],'67000')
            self.assertEqual(preview['margin_asset'],'INR')
            response=self.post('submit',{'token':preview['token'],'confirmed':True})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json()['order_id'],'order-1')
            self.assertNotIn(b'privatekey',response.data);self.assertNotIn(b'privatesecret',response.data)
            metadata.assert_called_once();self.assertEqual(plan.call_count,2)
            self.assertEqual(exchange.call_args_list[0].args[0],'POST')
            self.assertEqual(self.post('submit',{'token':preview['token'],'confirmed':True}).status_code,400)

    def test_documented_body_mode_uses_usdt_and_no_guessed_device_header(self):
        env={'SHARK_LIVE_TRADING_ENABLED':'1','SHARK_DEVICE_MODE':'DOCUMENTED_BODY','SHARK_MARGIN_ASSET':'USDT'}
        with patch.dict('os.environ',env,clear=True), patch.object(shark,'load_credentials',return_value={'api_key':'k','api_secret':'s'}), patch.object(shark,'verify_metadata'), patch.object(shark,'plan_order',side_effect=lambda creds,order,margin:{'order':dict(order),'intent':'OPEN','position':None}), patch.object(shark,'_request',side_effect=[{'clientOrderId':'order-1'}, {'clientOrderId':'order-1','status':'NEW'}, []]) as exchange:
            preview=self.post('preview',{'side':'BUY','type':'LIMIT','quantity':'0.002','price':'50000'}).get_json()
            response=self.post('submit',{'token':preview['token'],'confirmed':True})
            self.assertEqual(response.status_code,200)
            self.assertEqual(exchange.call_args_list[0].args[4]['deviceType'],'WEB')
            self.assertEqual(exchange.call_args_list[0].args[4]['userCategory'],'EXTERNAL')
            self.assertEqual(exchange.call_args_list[0].args[4]['marginAsset'],'USDT')
            self.assertEqual(exchange.call_args_list[0].kwargs['extra_headers'],{})

    def test_rejection_exposes_only_known_code_and_no_retry(self):
        env={'SHARK_LIVE_TRADING_ENABLED':'1','SHARK_DEVICE_MODE':'DOCUMENTED_BODY','SHARK_MARGIN_ASSET':'USDT'}
        with patch.dict('os.environ',env,clear=True), patch.object(shark,'load_credentials',return_value={'api_key':'k','api_secret':'s'}), patch.object(shark,'verify_metadata'), patch.object(shark,'plan_order',side_effect=lambda creds,order,margin:{'order':dict(order),'intent':'OPEN','position':None}), patch.object(shark,'_request',side_effect=shark.SharkAPIError('Shark reported error 3000: Incorrect device type reported by Shark.',exchange_code=3000)) as exchange:
            preview=self.post('preview',{'side':'BUY','type':'LIMIT','quantity':'0.002','price':'50000'}).get_json()
            response=self.post('submit',{'token':preview['token'],'confirmed':True})
            self.assertIn(b'3000',response.data)
            self.assertEqual(exchange.call_count,1)

    def test_metadata_failure_prevents_submission(self):
        env={'SHARK_LIVE_TRADING_ENABLED':'1','SHARK_DEVICE_HEADER_NAME':'X-Verified-Device','SHARK_DEVICE_HEADER_VALUE':'verified','SHARK_MARGIN_ASSET':'INR'}
        with patch.dict('os.environ',env), patch.object(shark,'load_credentials',return_value={'api_key':'k','api_secret':'s'}), patch.object(shark,'verify_metadata',side_effect=shark.SharkAPIError('invalid')), patch.object(shark,'plan_order',side_effect=lambda creds,order,margin:{'order':dict(order),'intent':'OPEN','position':None}), patch.object(shark,'_request') as exchange:
            preview=self.post('preview',{'side':'BUY','type':'LIMIT','quantity':'0.002','price':'50000'}).get_json()
            self.assertEqual(self.post('submit',{'token':preview['token'],'confirmed':True}).status_code,400)
            exchange.assert_not_called()

    def test_position_change_after_preview_never_submits(self):
        env={'SHARK_LIVE_TRADING_ENABLED':'1','SHARK_DEVICE_MODE':'DOCUMENTED_BODY','SHARK_MARGIN_ASSET':'INR'}
        position={'positionId':'pos-1','direction':'LONG','quantity':'0.002','marginAsset':'INR'}
        def reduce_plan(creds,order,margin):
            return {'order':{**order,'placeType':'POSITION','positionId':'pos-1','reduceOnly':True},'intent':'REDUCE','position':position}
        def flat_plan(creds,order,margin):
            return {'order':dict(order),'intent':'OPEN','position':None}
        with patch.dict('os.environ',env,clear=True), patch.object(shark,'load_credentials',return_value={'api_key':'k','api_secret':'s'}), patch.object(shark,'verify_metadata'), patch.object(shark,'plan_order',side_effect=[reduce_plan({'api_key':'k'},shark.build_order_preview('SELL','LIMIT','0.002','50000'),'INR'),flat_plan({'api_key':'k'},shark.build_order_preview('SELL','LIMIT','0.002','50000'),'INR')]), patch.object(shark,'_request') as exchange:
            preview=self.post('preview',{'side':'SELL','type':'LIMIT','quantity':'0.002','price':'50000'}).get_json()
            self.assertEqual(preview['intent'],'REDUCE')
            response=self.post('submit',{'token':preview['token'],'confirmed':True})
            self.assertIn(b'position changed',response.data)
            exchange.assert_not_called()

    def test_reduce_order_submits_only_position_bound_reduce_only_payload(self):
        env={'SHARK_LIVE_TRADING_ENABLED':'1','SHARK_DEVICE_MODE':'DOCUMENTED_BODY','SHARK_MARGIN_ASSET':'INR'}
        position={'positionId':'pos-1','direction':'LONG','quantity':'0.002','marginAsset':'INR'}
        def reduce_plan(creds,order,margin):
            return {'order':{**order,'placeType':'POSITION','positionId':'pos-1','reduceOnly':True},'intent':'REDUCE','position':position}
        with patch.dict('os.environ',env,clear=True), patch.object(shark,'load_credentials',return_value={'api_key':'k','api_secret':'s'}), patch.object(shark,'verify_metadata'), patch.object(shark,'plan_order',side_effect=reduce_plan), patch.object(shark,'_request',side_effect=[{'clientOrderId':'order-1'},{'clientOrderId':'order-1','status':'NEW'},[]]) as exchange:
            preview=self.post('preview',{'side':'SELL','type':'LIMIT','quantity':'0.002','price':'50000'}).get_json()
            self.assertEqual(preview['intent'],'REDUCE')
            self.assertEqual(self.post('submit',{'token':preview['token'],'confirmed':True}).status_code,200)
            payload=exchange.call_args_list[0].args[4]
            self.assertEqual(payload['placeType'],'POSITION')
            self.assertEqual(payload['positionId'],'pos-1')
            self.assertIs(payload['reduceOnly'],True)

    def test_disabled_by_default_and_export(self):
        with patch.dict('os.environ',{'SHARK_LIVE_TRADING_ENABLED':'0'}):
            self.assertEqual(self.post('submit',{'token':'x'}).status_code,403)
        self.assertIn(b'shark-csrf',self.c.get('/trading').data)
        app.config['STATIC_EXPORT']=True
        for path in ('/trading','/subscribe','/dashboard'):
            data=self.c.get(path).data
            self.assertNotIn(b'shark-csrf',data);self.assertNotIn(b'/local/shark',data);self.assertNotIn(b'Shark live account',data);self.assertNotIn(b'BTCUSDT account activity',data)
        self.assertEqual(self.c.get('/local/shark-script.js').status_code,404)
        app.config['STATIC_EXPORT']=False

if __name__ == '__main__': unittest.main()
