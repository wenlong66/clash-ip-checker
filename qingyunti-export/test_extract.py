import unittest
from unittest.mock import patch
import subprocess

from extract import RUNTIME_FIELDS, find_pid, main, parse_config, portable_config


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

    def test_removes_runtime_fields_and_preserves_nodes_and_rules(self):
        config = {key: "runtime value" for key in RUNTIME_FIELDS}
        config.update({"dns": {"proxy-server-nameserver": ["https://example.com/dns-query"]},
                       "proxies": [{"name": "test", "type": "vless", "server": "example.com"}],
                       "rules": ["MATCH,DIRECT"]})
        result = portable_config(config)
        self.assertTrue(all(key not in result for key in RUNTIME_FIELDS))
        self.assertEqual(result["dns"]["proxy-server-nameserver"], ["system"])
        self.assertEqual(result["proxies"], config["proxies"])
        self.assertEqual(result["rules"], config["rules"])
        self.assertIn("secret", config)


if __name__ == "__main__":
    unittest.main()
