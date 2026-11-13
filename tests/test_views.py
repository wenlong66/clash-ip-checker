import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.views import router


class PageTests(unittest.TestCase):
    def test_navigation_serves_separate_checker_and_failover_pages(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            checker = client.get('/')
            failover = client.get('/failover')
        self.assertEqual(checker.status_code, 200)
        self.assertEqual(failover.status_code, 200)
        self.assertIn('id="yaml-editor"', checker.text)
        self.assertNotIn('id="failover-heading"', checker.text)
        self.assertIn('id="failover-heading"', failover.text)
        self.assertNotIn('id="yaml-editor"', failover.text)
        self.assertIn('Loyalsoldier 白名单规则', failover.text)
        self.assertIn('href="/" aria-current="page"', checker.text)
        self.assertIn('href="/failover" aria-current="page"', failover.text)
        for page in (checker, failover):
            self.assertIn('x-ref="exportModal"', page.text)


if __name__ == '__main__':
    unittest.main()
