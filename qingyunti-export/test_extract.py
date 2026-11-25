import unittest
from unittest.mock import patch
import subprocess
import json

import extract as exporter
from extract import find_pid, main, parse_config, portable_config
from utils.clash_config import RUNTIME_FIELDS


class ExportTests(unittest.TestCase):
    def test_auto_detects_only_a_unique_process(self):
        with patch('extract.subprocess.run') as run:
            run.return_value.stdout = '1234\n'
            self.assertEqual(find_pid(), 1234)
            for output in ('', '1234\n5678\n'):
                run.return_value.stdout = output
                with self.assertRaises(RuntimeError):
                    find_pid()
            run.side_effect = subprocess.TimeoutExpired('powershell.exe', 15)
            with self.assertRaises(subprocess.TimeoutExpired):
                find_pid()

    def test_json_config_can_be_recovered_without_null_delimiters(self):
        config = {'proxies': [{'name': 'test', 'server': 'node.example.invalid', 'type': 'vless'}],
                  'dns': {'nameserver': ['system']}, 'rules': ['MATCH,DIRECT']}
        raw = b'prefix bytes' + json.dumps(config).encode() + b'\xfftrailing bytes'
        self.assertEqual(exporter.config_candidates(raw), [config])
        self.assertEqual(exporter.config_candidates(b'not a config'), [])

    def test_stdout_mode_does_not_write_a_file(self):
        config = {'proxies': [{'name': 'test', 'server': 'example.com', 'type': 'vless'}]}
        with patch('extract.sys.argv', ['extract.py', '--stdout']), \
                patch('extract.find_pid', return_value=1234), \
                patch('extract.extract', return_value=config) as extract, \
                patch('extract.Path.write_text') as write, \
                patch('extract.sys.stdout') as output:
            main()
        extract.assert_called_once_with(1234)
        write.assert_not_called()
        self.assertIn('proxies:', output.write.call_args.args[0])

    def test_rejects_incomplete_or_unrelated_data(self):
        for raw in [b"\xff", b"proxies: []", b"hello", b'{"proxies":[{"name":"test"}]}']:
            self.assertIsNone(parse_config(raw))

    def test_parses_json_and_yaml(self):
        expected = {"proxies": [{"name": "test", "type": "vless", "server": "example.com"}]}
        self.assertEqual(parse_config(b'proxies: [{name: test, type: vless, server: example.com}]'), expected)
        self.assertEqual(parse_config(b'{"proxies":[{"name":"test","type":"vless","server":"example.com"}]}'), expected)

    def test_exports_live_server_hosts_without_changing_tls_or_credentials(self):
        proxies = [
            {"name": "HK", "server": "nodes.example.invalid", "port": 10001, "type": "vless", "uuid": "test-id", "servername": "tls.example.invalid"},
            {"name": "JP", "server": "nodes.example.invalid", "port": 10002, "type": "vless"},
        ]
        config = {"proxies": proxies, "hosts": {"other.example.invalid": "192.0.2.9"},
                  "dns": {"proxy-server-nameserver": ["https://private.example.invalid/dns-query"]}}
        connections = [{"RemoteAddress": "192.0.2.1", "RemotePort": 10002},
                       {"RemoteAddress": "192.0.2.2", "RemotePort": 443}]
        with patch('extract.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(connections))) as run:
            hosts = exporter.active_server_hosts(1234, proxies)
        result = portable_config(config, hosts)
        self.assertEqual(result["hosts"], {"other.example.invalid": "192.0.2.9", "nodes.example.invalid": ["192.0.2.1"]})
        self.assertEqual(result["proxies"], proxies)
        self.assertEqual(config["hosts"], {"other.example.invalid": "192.0.2.9"})
        self.assertEqual(result["dns"]["proxy-server-nameserver"], config["dns"]["proxy-server-nameserver"])
        self.assertIn('1234', run.call_args.args[0][-1])
        self.assertEqual(run.call_args.kwargs['timeout'], 15)
        self.assertTrue(run.call_args.kwargs['check'])

    def test_rejects_missing_ambiguous_and_invalid_live_connections(self):
        proxies = [{"name": "HK", "server": "nodes.example.invalid", "port": 10001}]
        for connections in ([], [{"RemoteAddress": "192.0.2.1", "RemotePort": 443}],
                            [{"RemoteAddress": "not-an-ip", "RemotePort": 10001}], {}):
            with self.subTest(connections=connections), \
                    patch('extract.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(connections))):
                with self.assertRaises(RuntimeError):
                    exporter.active_server_hosts(1234, proxies)
        ambiguous = [*proxies, {"name": "JP", "server": "other.example.invalid", "port": 10001}]
        with patch('extract.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '[{"RemoteAddress":"192.0.2.1","RemotePort":10001}]')):
            with self.assertRaises(RuntimeError):
                exporter.active_server_hosts(1234, ambiguous)
        with patch('extract.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '[]')):
            self.assertEqual(exporter.active_server_hosts(1234, [{"server": "2001:db8::1", "port": 10001}]), {})

    def test_preserves_portable_tun_dns_and_sniffer_without_client_bindings(self):
        config = {'tun': {'enable': True, 'device': 'apex-tun', 'file-descriptor': 123,
                          'stack': 'mixed', 'auto-route': True, 'dns-hijack': ['any:53']},
                  'dns': {'enable': True, 'listen': '127.0.0.1:1053', 'enhanced-mode': 'fake-ip',
                          'nameserver': ['https://doh.pub/dns-query'],
                          'proxy-server-nameserver': ['https://223.5.5.5/dns-query']},
                  'sniffer': {'enable': True, 'sniff': {'TLS': {'ports': [443]}}},
                  'ipv6': True}
        result = portable_config(config, {'node.example.com': ['192.0.2.1']})
        self.assertEqual(result['tun'], {'enable': True, 'stack': 'mixed', 'auto-route': True,
                                         'dns-hijack': ['any:53']})
        self.assertNotIn('listen', result['dns'])
        self.assertTrue(result['dns']['use-hosts'])
        self.assertEqual(result['dns']['nameserver'], config['dns']['nameserver'])
        self.assertEqual(result['sniffer'], config['sniffer'])
        self.assertTrue(result['ipv6'])
        self.assertIn('device', config['tun'])
        self.assertIn('listen', config['dns'])

    def test_removes_runtime_fields_and_preserves_nodes_and_rules(self):
        config = {key: "runtime value" for key in RUNTIME_FIELDS}
        config.update({"dns": {"proxy-server-nameserver": ["https://example.com/dns-query"]},
                       "proxies": [{"name": "test", "type": "vless", "server": "example.com"}],
                       "rules": ["MATCH,DIRECT"]})
        result = portable_config(config)
        self.assertTrue(all(key not in result for key in RUNTIME_FIELDS))
        self.assertEqual(result["dns"]["proxy-server-nameserver"], config["dns"]["proxy-server-nameserver"])
        self.assertEqual(result["proxies"], config["proxies"])
        self.assertEqual(result["rules"], config["rules"])
        self.assertIn("secret", config)


if __name__ == "__main__":
    unittest.main()
