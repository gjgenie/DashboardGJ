import unittest
from app import app

class RouteTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_auth_and_navigation(self):
        self.assertEqual(self.client.get('/dashboard').status_code, 302)
        self.assertEqual(self.client.post('/', data={'email':'wrong','password':'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/', data={'email':'student@gjacademy.com','password':'Demo@123'}).status_code, 302)
        for path in ('strategies','strategy_details?id=time-machine','subscribe?id=time-machine','dashboard','trading','orders','analytics','settings'):
            self.assertEqual(self.client.get('/'+path).status_code, 200, path)
        self.client.post('/logout')
        self.assertEqual(self.client.get('/dashboard').status_code, 302)

if __name__ == '__main__':
    unittest.main()
