import unittest
from app import app

class RouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, STATIC_EXPORT=False)
        self.client = app.test_client()

    def test_direct_local_navigation_and_session(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        for path in ('strategies','strategy_details?id=time-machine','subscribe?id=time-machine','dashboard','trading','orders','analytics','settings'):
            self.assertEqual(self.client.get('/'+path).status_code, 200, path)
        with self.client.session_transaction() as session:
            self.assertTrue(session.get('sid'))
            self.assertTrue(session.get('csrf'))
        self.assertNotIn(b'Log out', self.client.get('/dashboard').data)

    def test_shark_post_requires_initialized_local_session_and_csrf(self):
        fresh = app.test_client()
        self.assertEqual(fresh.post('/local/shark/status',json={},headers={'Origin':'http://localhost'}).status_code,401)
        fresh.get('/dashboard')
        self.assertEqual(fresh.post('/local/shark/status',json={},headers={'Origin':'http://localhost'}).status_code,403)
        self.assertEqual(fresh.get('/dashboard',headers={'Host':'evil.test'}).status_code,403)

    def test_theme_controls_are_available(self):
        dashboard = self.client.get('/dashboard')
        self.assertIn(b'themes.css', dashboard.data)
        self.assertIn(b'js/theme.js', dashboard.data)
        self.assertIn(b'data-theme-toggle', dashboard.data)

    def test_static_export_keeps_separate_demo_login(self):
        app.config['STATIC_EXPORT'] = True
        try:
            fresh = app.test_client()
            self.assertIn(b'Sign in',fresh.get('/').data)
            self.assertEqual(fresh.get('/dashboard').status_code,302)
        finally:
            app.config['STATIC_EXPORT'] = False

if __name__ == '__main__':
    unittest.main()
