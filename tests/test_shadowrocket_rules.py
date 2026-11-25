from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from test_geosite import geosite_fixture
from utils.shadowrocket_rules import shadowrocket_rules_config


class ShadowrocketRulesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'GeoSite.dat'
        self.database.write_bytes(geosite_fixture())
        self.config = {
            'secret': 'controller-secret', 'ipv6': True,
            'proxies': [{'name': 'Japan', 'type': 'vless', 'uuid': 'never-export-this-uuid',
                         'password': 'never-export-this-password', 'server': 'node.example.com'}],
            'proxy-groups': [{'name': '青云出口', 'type': 'select', 'proxies': ['Japan']}],
            'dns': {'enable': True, 'ipv6': True, 'enhanced-mode': 'fake-ip',
                    'nameserver': ['https://doh.pub/dns-query', 'tls://223.5.5.5:853'],
                    'proxy-server-nameserver': ['system'], 'fake-ip-filter': ['+.lan', 'localhost']},
            'hosts': {'service.example.com': ['192.0.2.1', '192.0.2.2']},
            'rules': ['DOMAIN-SUFFIX,cn,DIRECT', 'GEOSITE,test@cn,DIRECT',
                      'IP-CIDR6,fc00::/7,DIRECT,no-resolve',
                      'AND,((NETWORK,UDP),(DST-PORT,443)),REJECT',
                      'DOMAIN,service.example.com,Japan', 'MATCH,青云出口'],
        }

    def test_policy_file_embeds_dns_hosts_and_rules_but_no_nodes_or_credentials(self):
        original = deepcopy(self.config)
        text = shadowrocket_rules_config(self.config, self.database)
        self.assertIn('[General]', text)
        self.assertIn('[Rule]', text)
        self.assertIn('[Host]', text)
        self.assertNotIn('[Proxy]', text)
        self.assertNotIn('[Proxy Group]', text)
        for secret in ('never-export-this-uuid', 'never-export-this-password', 'controller-secret', 'vless://'):
            self.assertNotIn(secret, text)
        self.assertIn('dns-server = https://doh.pub/dns-query,tls://223.5.5.5:853', text)
        self.assertIn('proxy-dns-server = system', text)
        self.assertIn('dns-direct-system = false', text)
        self.assertIn('dns-direct-fallback-proxy = false', text)
        self.assertIn('ipv6 = true', text)
        self.assertIn('always-real-ip = lan,*.lan,localhost', text)
        self.assertIn('DOMAIN-SUFFIX,example.cn,DIRECT', text)
        self.assertIn('IP-CIDR,fc00::/7,DIRECT,no-resolve', text)
        self.assertIn('AND,((PROTOCOL,UDP),(DST-PORT,443)),REJECT', text)
        self.assertIn('DOMAIN,service.example.com,PROXY', text)
        self.assertIn('FINAL,PROXY', text)
        self.assertIn('service.example.com = 192.0.2.1', text)
        self.assertIn('当前选中', text)
        self.assertIn('HTTP/HTTPS', text)
        self.assertNotIn('GEOSITE,', text)
        self.assertNotIn('DOMAIN-REGEX,', text)
        self.assertLess(text.index('DOMAIN-SUFFIX,cn,DIRECT'), text.index('DOMAIN-SUFFIX,example.cn,DIRECT'))
        self.assertLess(text.index('DOMAIN-SUFFIX,example.cn,DIRECT'), text.index('FINAL,PROXY'))
        self.assertEqual(self.config, original)

    def test_frozen_geodata_remains_usable_without_the_original_database(self):
        from utils.qingyunti_geodata import qingyunti_geodata
        pinned = qingyunti_geodata(self.config, self.database.parent)
        self.database.unlink()
        text = shadowrocket_rules_config(pinned, self.database)
        self.assertIn('DOMAIN-SUFFIX,example.cn,DIRECT', text)
        self.assertIn('URL-REGEX,', text)
        self.assertIn('FINAL,PROXY', text)
        self.assertNotIn('RULE-SET,', text)
        self.assertNotIn('never-export-this', text)

    def test_invalid_inline_networks_are_not_exported_as_valid_rules(self):
        for value in ('not-a-network', '192.0.2.0/24,REJECT'):
            source = {**self.config, 'rules': ['RULE-SET,local,DIRECT'], 'rule-providers': {
                'local': {'type': 'inline', 'behavior': 'ipcidr', 'payload': [value]}}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                shadowrocket_rules_config(source, None)

    def test_comma_quantifier_is_rejected_instead_of_silently_rewritten(self):
        source = {**self.config, 'rules': ['RULE-SET,local,DIRECT'], 'rule-providers': {
            'local': {'type': 'inline', 'behavior': 'classical',
                      'payload': [r'DOMAIN-REGEX,^a{1,3}\.example\.invalid$']}}}
        with self.assertRaises(ValueError):
            shadowrocket_rules_config(source, None)

    def test_dns_fallback_does_not_add_system_resolver_and_explicit_fallback_is_kept(self):
        self.config['rules'] = ['MATCH,青云出口']
        text = shadowrocket_rules_config(self.config, None)
        self.assertIn('fallback-dns-server = https://doh.pub/dns-query,tls://223.5.5.5:853', text)
        self.config['dns']['fallback'] = ['https://dns.example.com/dns-query']
        text = shadowrocket_rules_config(self.config, None)
        self.assertIn('fallback-dns-server = https://dns.example.com/dns-query', text)

    def test_invalid_or_untranslatable_policies_fail_without_node_credentials(self):
        for change in (
            {'rules': ['MATCH,missing']}, {'rules': ['PROCESS-NAME,app.exe,DIRECT']},
            {'rules': ['RULE-SET,local,DIRECT']}, {'rules': ['GEOSITE,DIRECT']},
            {'rules': ['MATCH,青云出口\n[Proxy]']},
            {'dns': {'nameserver': ['system'], 'nameserver-policy': {'+.cn': ['system']}}},
            {'dns': {'nameserver': ['system'], 'fake-ip-filter-mode': 'whitelist'}},
            {'dns': {'nameserver': ['system\n[Proxy]']}},
            {'dns': {'nameserver': ['https://dns.example.com#青云出口']}},
            {'hosts': {'service.example.com': 'not-an-ip'}},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError) as error:
                shadowrocket_rules_config({**self.config, **change}, self.database)
            self.assertNotIn('never-export-this', str(error.exception))


if __name__ == '__main__':
    unittest.main()
