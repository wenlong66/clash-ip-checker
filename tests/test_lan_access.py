import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from web import app


class LanAccessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        (self.root / 'exports').mkdir()
        (self.root / 'private_exports').mkdir()
        self.token = 'a' * 32
        (self.root / 'private_exports' / f'qingyunti_{self.token}.yaml').write_text('proxies: []\n')
        network = patch('utils.network.lan_ip', return_value='10.12.64.8')
        network.start()
        self.addCleanup(network.stop)

    def client(self, address):
        return TestClient(app, base_url='http://10.12.64.8:18080', client=(address, 54321))

    def test_remote_lan_download_is_allowed_but_all_operations_are_denied(self):
        remote = self.client('10.12.64.9')
        response = remote.get(f'/api/qingyunti/download/{self.token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, 'proxies: []\n')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        with patch('routers.qingyunti.subprocess.run') as extract:
            for method, path in [('GET', '/'), ('GET', '/api/nodes'), ('GET', '/api/failover/profiles'),
                                 ('POST', '/api/start'), ('POST', '/api/export'),
                                 ('POST', '/api/qingyunti/export'), ('GET', '/openapi.json'),
                                 ('POST', '/exports/test.yaml')]:
                with self.subTest(path=path):
                    self.assertEqual(remote.request(method, path).status_code, 403)
            extract.assert_not_called()
        self.assertEqual(remote.get('/exports/not-found.yaml').status_code, 404)
        self.assertEqual(remote.get('/exports/').status_code, 404)

    def test_local_lan_browser_works_without_allowing_forged_forwarded_headers(self):
        local = self.client('10.12.64.8')
        self.assertEqual(local.get('/failover').status_code, 200)
        self.assertEqual(local.get('/api/nodes').status_code, 200)
        self.assertEqual(local.get('/api/nodes', headers={'origin': 'http://attacker.invalid'}).status_code, 403)
        remote = self.client('10.12.64.9')
        self.assertEqual(remote.get('/api/nodes', headers={'x-forwarded-for': '127.0.0.1'}).status_code, 403)
        self.assertEqual(remote.get(f'/api/qingyunti/download/{self.token}',
                                   headers={'host': 'attacker.invalid'}).status_code, 403)

    def test_public_clients_cannot_download_exports(self):
        self.assertEqual(self.client('8.8.8.8').get(f'/api/qingyunti/download/{self.token}').status_code, 403)
        self.assertEqual(self.client('8.8.8.8').get('/exports/not-found.yaml').status_code, 403)
