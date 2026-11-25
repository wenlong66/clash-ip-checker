from copy import deepcopy
from pathlib import Path
import re
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
        self.assertIn('DOMAIN,a1.example.cn,DIRECT', text)
        self.assertIn('DOMAIN,a5.example.cn,DIRECT', text)
        self.assertNotIn('URL-REGEX,', text)
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
        self.assertIn('DOMAIN,a1.example.cn,DIRECT', text)
        self.assertIn('FINAL,PROXY', text)
        self.assertNotIn('RULE-SET,', text)
        self.assertNotIn('never-export-this', text)

    def test_invalid_inline_networks_are_not_exported_as_valid_rules(self):
        for value in ('not-a-network', '192.0.2.0/24,REJECT'):
            source = {**self.config, 'rules': ['RULE-SET,local,DIRECT'], 'rule-providers': {
                'local': {'type': 'inline', 'behavior': 'ipcidr', 'payload': [value]}}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                shadowrocket_rules_config(source, None)

    def test_finite_regex_matches_exact_domains_and_suffixes_for_all_protocols(self):
        for expression in (r'^a{1,3}\.example\.invalid$',
                           r'(^|\.)node[1-3]{1,2}\.(com|net)$',
                           r'^edge\d?\.example\.invalid$'):
            source = {**self.config, 'rules': ['DOMAIN,before.invalid,REJECT',
                'RULE-SET,local,DIRECT', 'MATCH,青云出口'], 'rule-providers': {
                'local': {'type': 'inline', 'behavior': 'classical',
                          'payload': ['DOMAIN-REGEX,' + expression]}}}
            original = deepcopy(source)
            text = shadowrocket_rules_config(source, None)
            rules = text.split('[Rule]\n', 1)[1].split('\n\n', 1)[0].splitlines()
            self.assertEqual(rules[0], 'DOMAIN,before.invalid,REJECT')
            self.assertEqual(rules[-1], 'FINAL,PROXY')
            converted = [line.split(',') for line in rules[1:-1]]
            self.assertTrue(converted)
            self.assertTrue(all(kind in ('DOMAIN', 'DOMAIN-SUFFIX') for kind, _, _ in converted))
            for host in ('a.example.invalid', 'aa.example.invalid', 'aaa.example.invalid',
                         'aaaa.example.invalid', 'sub.a.example.invalid', 'a.example.invalid.evil',
                         'node1.com', 'node12.net', 'www.node33.com', 'node4.com',
                         'node123.com', 'mynode1.com', 'node1.com.evil', 'edge.example.invalid',
                         'edge0.example.invalid', 'edge12.example.invalid'):
                expected = bool(re.search(expression, host))
                actual = any(host == value or kind == 'DOMAIN-SUFFIX' and host.endswith('.' + value)
                             for kind, value, _ in converted)
                with self.subTest(expression=expression, host=host):
                    self.assertEqual(actual, expected)
            self.assertNotIn('URL-REGEX,', text)
            self.assertEqual(source, original)

    def test_unbounded_regex_retains_http_warning_and_comma_quantifier_semantics(self):
        for expression in (r'^a+\d{1,3}\.example\.invalid$',
                           r'^a+\d{2,}\.example\.invalid$',
                           r'^a+[0-9]{1,3}\.example\.invalid$',
                           r'^a+b{1,3}\.example\.invalid$'):
            source = {**self.config, 'rules': ['DOMAIN-REGEX,' + expression + ',DIRECT']}
            text = shadowrocket_rules_config(source, None)
            rule = next(line for line in text.splitlines() if line.startswith('URL-REGEX,'))
            _, converted, target = rule.split(',')
            self.assertEqual(target, 'DIRECT')
            self.assertIn('HTTP/HTTPS', text)
            for host in ('a1.example.invalid', 'aaa12.example.invalid', 'a123.example.invalid',
                         'a1234.example.invalid', 'a.example.invalid', 'a12.example.invalid.evil',
                         'aab.example.invalid', 'aabbb.example.invalid', 'aabbbb.example.invalid'):
                with self.subTest(expression=expression, host=host):
                    self.assertEqual(bool(re.search(converted, 'https://' + host + '/path')),
                                     bool(re.search(expression, host)))

    def test_large_finite_regex_uses_warned_fallback_instead_of_exploding_config(self):
        source = {**self.config, 'rules': [r'DOMAIN-REGEX,^n[0-9]{1,4}\.example\.invalid$,DIRECT']}
        text = shadowrocket_rules_config(source, None)
        rules = text.split('[Rule]\n', 1)[1].split('\n\n', 1)[0].splitlines()
        self.assertEqual(len(rules), 1)
        self.assertTrue(rules[0].startswith('URL-REGEX,'))
        self.assertIn('HTTP/HTTPS', text)
        _, expression, _ = rules[0].split(',')
        self.assertTrue(re.search(expression, 'https://n1234.example.invalid/'))
        self.assertFalse(re.search(expression, 'https://n12345.example.invalid/'))

    def test_excessive_regex_expansion_is_rejected_without_allocating_the_output(self):
        source = {**self.config, 'rules': [r'DOMAIN-REGEX,^a{1,99999999}\.invalid$,DIRECT']}
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
