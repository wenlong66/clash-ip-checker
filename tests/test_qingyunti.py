import subprocess
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import qingyunti
from routers.views import router as views_router
from test_geosite import geosite_fixture


class QingyuntiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous = Path.cwd()
        os.chdir(temporary.name)
        self.addCleanup(os.chdir, previous)
        app = FastAPI()
        app.include_router(qingyunti.router)
        app.include_router(views_router)
        self.client = TestClient(app, base_url='http://127.0.0.1:18080', client=('127.0.0.1', 54321))
        network_patch = patch('utils.network.lan_ip', return_value='10.12.64.8')
        network_patch.start()
        self.addCleanup(network_patch.stop)
        self.config = 'proxies:\n- {name: 测试, type: vless, server: example.invalid}\nrules: [MATCH,DIRECT]\n'
        runner = patch.object(qingyunti.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, self.config, ''))
        self.run = runner.start()
        self.addCleanup(runner.stop)

    def test_export_and_protected_download_preserve_yaml_in_private_files(self):
        response = self.client.post('/api/qingyunti/export')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['node_count'], 1)
        self.assertEqual(data['yaml'], self.config)
        self.assertRegex(data['filename'], r'^qingyunti_[0-9a-f]{32}\.yaml$')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual((Path('private_exports') / data['filename']).read_text(encoding='utf-8'), self.config)
        self.assertFalse(Path('exports').exists())
        self.assertIn('--stdout', self.run.call_args.args[0])
        self.assertEqual(self.run.call_args.kwargs['timeout'], 90)
        downloaded = self.client.get(data['url'])
        self.assertEqual(downloaded.text, self.config)
        self.assertEqual(downloaded.headers['cache-control'], 'no-store')
        self.client.post('/api/qingyunti/export')
        self.assertEqual(self.client.get(data['url']).text, self.config)

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
                                ('未找到节点服务器的活动连接', '连接一个节点'),
                                ('CalledProcessError: Get-NetTCPConnection', '连接一个节点'),
                                ('无法唯一匹配 Apex 活动节点地址', '唯一匹配'),
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

    def test_shadowrocket_download_converts_saved_nodes_and_is_local_only(self):
        self.run.return_value = subprocess.CompletedProcess([], 0,
            'proxies:\n- {name: Japan, type: vless, server: node.example.com, port: 443, '
            'uuid: 9cb2e553-82f9-4f4f-95c3-6e013c2d49af, tls: true, servername: tls.example.com, '
            'flow: xtls-rprx-vision, skip-cert-verify: true, udp: true}\n'
            'hosts: {node.example.com: [192.0.2.1]}\n', '')
        exported = self.client.post('/api/qingyunti/export').json()
        url = exported['url'] + '/shadowrocket.txt'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('@192.0.2.1:443?', response.text)
        self.assertIn('sni=tls.example.com', response.text)
        self.assertIn('flow=xtls-rprx-vision', response.text)
        self.assertIn('allowInsecure=1', response.text)
        self.assertIn('udp=1', response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertIn('qingyunti-shadowrocket.txt', response.headers['content-disposition'])
        remote = TestClient(self.client.app, base_url='http://127.0.0.1', client=('192.0.2.1', 54321))
        self.assertEqual(remote.get(url).status_code, 403)
        self.assertEqual(self.client.get('/api/qingyunti/download/invalid/shadowrocket.txt').status_code, 404)
        self.run.return_value = subprocess.CompletedProcess([], 0, self.config, '')
        invalid = self.client.post('/api/qingyunti/export').json()
        self.assertEqual(self.client.get(invalid['url'] + '/shadowrocket.txt').status_code, 400)

    def test_separate_dns_rules_download_excludes_nodes_and_preserves_txt_subscription(self):
        self.run.return_value = subprocess.CompletedProcess([], 0,
            'proxies:\n- {name: Japan, type: vless, server: node.example.com, port: 443, '
            'uuid: 9cb2e553-82f9-4f4f-95c3-6e013c2d49af, tls: true, servername: tls.example.com}\n'
            'hosts: {node.example.com: [192.0.2.1]}\n'
            'dns: {enable: true, nameserver: [https://doh.pub/dns-query]}\n'
            'proxy-groups: [{name: 青云出口, type: select, proxies: [Japan]}]\n'
            'rules: ["GEOSITE,test@cn,DIRECT", "MATCH,青云出口"]\n', '')
        exported = self.client.post('/api/qingyunti/export').json()
        txt = self.client.get(exported['url'] + '/shadowrocket.txt').text
        url = exported['url'] + '/shadowrocket-rules.conf'
        database = Path('GeoSite.dat')
        database.write_bytes(geosite_fixture())
        with patch.object(qingyunti, 'GEOSITE_PATH', database):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn('[General]', response.text)
            self.assertIn('DOMAIN-SUFFIX,example.cn,DIRECT', response.text)
            self.assertIn('FINAL,PROXY', response.text)
            for secret in ('9cb2e553', 'vless://', '[Proxy]', '[Proxy Group]'):
                self.assertNotIn(secret, response.text)
            self.assertIn('qingyunti-shadowrocket-rules.conf', response.headers['content-disposition'])
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(self.client.get(exported['url'] + '/shadowrocket.txt').text, txt)
            database.unlink()
            failed = self.client.get(url)
            self.assertEqual(failed.status_code, 400)
            self.assertNotIn('9cb2e553', failed.text)
        remote = TestClient(self.client.app, base_url='http://127.0.0.1', client=('192.0.2.1', 54321))
        self.assertEqual(remote.get(url).status_code, 403)
        self.assertEqual(self.client.get('/api/qingyunti/download/invalid/shadowrocket-rules.conf').status_code, 404)
        self.assertEqual(self.client.get('/api/qingyunti/download/' + 'a' * 32 + '/shadowrocket-rules.conf').status_code, 404)

    def test_shadowrocket_complete_config_download_is_not_exposed(self):
        response = self.client.get('/api/qingyunti/download/' + 'a' * 32 + '/shadowrocket.conf')
        self.assertEqual(response.status_code, 404)

    def test_dedicated_page_has_export_controls_shared_modal_and_navigation(self):
        page = self.client.get('/qingyunti')
        self.assertEqual(page.status_code, 200)
        for text in ('<title>梯子导出</title>', 'id="qingyunti-heading"', 'x-ref="exportModal"',
                     'href="/qingyunti" aria-current="page"', '@click="exportQingyunti"',
                     '@click="refreshClashSubscription"', '@click.prevent="downloadShadowrocket()"',
                     "@click.prevent=\"downloadShadowrocket('rules')\"",
                     'Shadowrocket 节点订阅 .txt', 'DNS 与分流 .conf',
                     '<small class="export-download-links" x-show="exportKind === \'qingyunti\'"'):
            self.assertIn(text, page.text)
        links = page.text.split('<small class="export-download-links"', 1)[1].split('</small>', 1)[0]
        self.assertEqual(links.count('<a '), 2)
        self.assertNotIn('<button', links)
        self.assertNotIn('role="button"', links)
        self.assertIn("exportUrl + '/shadowrocket.txt'", links)
        self.assertIn("exportUrl + '/shadowrocket-rules.conf'", links)
        self.assertLess(page.text.index('@click="copyYaml"'), page.text.index('@click.prevent="downloadShadowrocket()"'))
        self.assertNotIn('id="yaml-editor"', page.text)
        self.assertNotIn('id="failover-heading"', page.text)
        self.assertNotIn('完整配置 .conf', page.text)
        self.assertNotIn("downloadShadowrocket('conf')", page.text)


if __name__ == '__main__':
    unittest.main()
