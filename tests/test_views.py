from hashlib import sha256
from pathlib import Path
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
        self.assertIn('@click="loadNodes"', checker.text)
        self.assertIn('检测选中', checker.text)
        self.assertIn('x-text="node.status"', checker.text)
        self.assertIn('x-text="node.error"', checker.text)
        self.assertNotIn("'degraded': node.source !== 'ping0'", checker.text)
        self.assertNotIn('id="failover-heading"', checker.text)
        self.assertIn('id="failover-heading"', failover.text)
        self.assertNotIn('id="yaml-editor"', failover.text)
        self.assertIn('Loyalsoldier 白名单规则', failover.text)
        self.assertIn('href="/" aria-current="page"', checker.text)
        self.assertIn('href="/failover" aria-current="page"', failover.text)
        for page in (checker, failover):
            self.assertIn('x-ref="exportModal"', page.text)
            self.assertIn('@click="refreshClashSubscription"', page.text)

    def test_shared_page_script_url_changes_with_its_content(self):
        app = FastAPI()
        app.include_router(router)
        script = Path(__file__).resolve().parents[1] / 'static/js/app.js'
        version = sha256(script.read_bytes()).hexdigest()[:12]
        with TestClient(app) as client:
            for path in ('/', '/failover', '/qingyunti'):
                with self.subTest(path=path):
                    self.assertIn(f'src="/static/js/app.js?v={version}"', client.get(path).text)


if __name__ == '__main__':
    unittest.main()
