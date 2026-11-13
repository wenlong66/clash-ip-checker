import unittest

from extract import RUNTIME_FIELDS, parse_config, portable_config


class ExportTests(unittest.TestCase):
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
