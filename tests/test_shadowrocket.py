from copy import deepcopy
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from utils.shadowrocket import shadowrocket_subscription


class ShadowrocketTests(unittest.TestCase):
    def setUp(self):
        self.node = {'name': '日本 01', 'type': 'vless', 'server': 'node.example.com', 'port': 443,
                     'uuid': '9cb2e553-82f9-4f4f-95c3-6e013c2d49af', 'network': 'tcp', 'tls': True,
                     'servername': 'tls.example.com', 'flow': 'xtls-rprx-vision', 'skip-cert-verify': True}
        self.config = {'proxies': [self.node], 'hosts': {'node.example.com': ['192.0.2.1', '192.0.2.2']},
                       'secret': 'never-export', 'rules': ['MATCH,DIRECT']}

    def test_uses_actual_ip_preserves_tls_and_credentials_without_mutating_source(self):
        original = deepcopy(self.config)
        text = shadowrocket_subscription(self.config)
        uri = urlsplit(text.strip())
        self.assertEqual((uri.hostname, uri.port, uri.username),
                         ('192.0.2.1', 443, self.node['uuid']))
        self.assertEqual(unquote(uri.fragment), '日本 01')
        self.assertEqual(parse_qs(uri.query), {'encryption': ['none'], 'security': ['tls'], 'type': ['tcp'],
            'sni': ['tls.example.com'], 'flow': ['xtls-rprx-vision'], 'allowInsecure': ['1']})
        self.assertNotIn('never-export', text)
        self.assertNotIn('MATCH', text)
        self.assertEqual(self.config, original)
        config = {**self.config, 'hosts': {'node.example.com': '2001:db8::1'}}
        self.assertEqual(urlsplit(shadowrocket_subscription(config).strip()).hostname, '2001:db8::1')
        secure = {**self.node, 'server': '192.0.2.3', 'skip-cert-verify': False, 'flow': ''}
        self.assertNotIn('allowInsecure', shadowrocket_subscription({'proxies': [secure]}))

    def test_rejects_unsupported_and_incomplete_nodes_without_exposing_credentials(self):
        for changed in ({'type': 'trojan'}, {'tls': False}, {'network': 'ws'}, {'port': 0}, {'port': True},
                        {'uuid': 'secret-uuid'}, {'flow': 'unknown'}, {'name': 'bad\nname'},
                        {'servername': 'bad?domain'}, {'reality-opts': {'public-key': 'secret'}},
                        {'dialer-proxy': 'upstream'}, {'skip-cert-verify': 'true'}):
            with self.assertRaises(ValueError) as error:
                shadowrocket_subscription({**self.config, 'proxies': [{**self.node, **changed}]})
            self.assertNotIn('secret', str(error.exception))
        for config in ({'proxies': []}, {'proxies': [self.node]}, {**self.config, 'hosts': []},
                       {**self.config, 'hosts': {'node.example.com': []}}):
            with self.assertRaises(ValueError):
                shadowrocket_subscription(config)


if __name__ == '__main__':
    unittest.main()
