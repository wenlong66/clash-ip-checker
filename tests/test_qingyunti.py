import subprocess
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import qingyunti
from routers.views import router as views_router


class QingyuntiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(qingyunti.router)
        app.include_router(views_router)
        self.client = TestClient(app, base_url='http://127.0.0.1:18080', client=('127.0.0.1', 54321))
        self.config = 'proxies:\n- {name: 测试, type: vless, server: example.invalid}\nrules: [MATCH,DIRECT]\n'
        runner = patch.object(qingyunti.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, self.config, ''))
        self.run = runner.start()
        self.addCleanup(runner.stop)
        saved = patch.object(qingyunti, 'latest_export', None)
        saved.start()
        self.addCleanup(saved.stop)

    def test_export_and_protected_download_preserve_yaml_without_writing_files(self):
        with patch('pathlib.Path.write_text') as write:
            response = self.client.post('/api/qingyunti/export')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['node_count'], 1)
        self.assertEqual(data['yaml'], self.config)
        self.assertEqual(data['filename'], 'qingyunti-clash.yaml')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        write.assert_not_called()
        self.assertIn('--stdout', self.run.call_args.args[0])
        self.assertEqual(self.run.call_args.kwargs['timeout'], 90)
        downloaded = self.client.get(data['url'])
        self.assertEqual(downloaded.text, self.config)
        self.assertEqual(downloaded.headers['cache-control'], 'no-store')
        self.client.post('/api/qingyunti/export')
        self.assertEqual(self.client.get(data['url']).status_code, 404)

    def test_rejects_remote_clients_hosts_and_cross_origin_requests_before_extraction(self):
        for headers in ({'host': 'example.invalid'}, {'origin': 'https://example.invalid'},
                        {'origin': 'http://127.0.0.1:9999'}):
            self.assertEqual(self.client.post('/api/qingyunti/export', headers=headers).status_code, 403)
            self.assertEqual(self.client.get('/api/qingyunti/download/token', headers=headers).status_code, 403)
        remote = TestClient(self.client.app, base_url='http://127.0.0.1', client=('192.0.2.1', 54321))
        self.assertEqual(remote.post('/api/qingyunti/export').status_code, 403)
        self.run.assert_not_called()

    def test_failure_messages_do_not_expose_script_output_and_allow_retry(self):
        for stderr, message in [('未找到 ApexCore', '未找到 ApexCore'),
                                ('多个 ApexCore', '多个 ApexCore'),
                                ('PermissionError: WinError 5', '权限'),
                                ('PID does not belong', '安装路径'),
                                ("No module named 'yaml'", '依赖缺失'),
                                ('unrelated sensitive output', '未能提取完整配置')]:
            self.run.return_value = subprocess.CompletedProcess([], 1, '', stderr)
            response = self.client.post('/api/qingyunti/export')
            self.assertEqual(response.status_code, 400)
            self.assertIn(message, response.json()['detail'])
            self.assertNotIn('sensitive output', response.text)
        self.run.return_value = subprocess.CompletedProcess([], 0, self.config, '')
        self.assertEqual(self.client.post('/api/qingyunti/export').status_code, 200)

    def test_timeout_start_failure_invalid_output_and_busy_state(self):
        for error, status in [(subprocess.TimeoutExpired('extract', 90), 504), (OSError(), 500)]:
            self.run.side_effect = error
            self.assertEqual(self.client.post('/api/qingyunti/export').status_code, status)
        self.run.side_effect = None
        for output in ('invalid: [', 'hello', 'proxies: []'):
            self.run.return_value = subprocess.CompletedProcess([], 0, output, '')
            self.assertEqual(self.client.post('/api/qingyunti/export').status_code, 502)
        with qingyunti.export_lock:
            self.assertEqual(self.client.post('/api/qingyunti/export').status_code, 409)

    def test_dedicated_page_has_export_controls_shared_modal_and_navigation(self):
        page = self.client.get('/qingyunti')
        self.assertEqual(page.status_code, 200)
        for text in ('<title>梯子导出</title>', 'id="qingyunti-heading"', 'x-ref="exportModal"',
                     'href="/qingyunti" aria-current="page"', '@click="exportQingyunti"'):
            self.assertIn(text, page.text)
        self.assertNotIn('id="yaml-editor"', page.text)
        self.assertNotIn('id="failover-heading"', page.text)


if __name__ == '__main__':
    unittest.main()
