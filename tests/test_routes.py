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

    def test_theme_controls_are_available(self):
        login = self.client.get('/')
        self.assertIn(b'themes.css', login.data)
        self.assertIn(b'data-theme-toggle', login.data)
        self.client.post('/', data={'email':'student@gjacademy.com','password':'Demo@123'})
        dashboard = self.client.get('/dashboard')
        self.assertIn(b'themes.css', dashboard.data)
        self.assertIn(b'js/theme.js', dashboard.data)
        self.assertIn(b'data-theme-toggle', dashboard.data)

if __name__ == '__main__':
    unittest.main()
