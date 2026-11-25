import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from utils import qingyunti_geodata as geodata_module

from test_geosite import geosite_fixture
from test_geoip import geoip_fixture
from utils.qingyunti_geodata import qingyunti_geodata


class QingyuntiGeodataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        (self.directory / 'GeoSite.dat').write_bytes(geosite_fixture())
        (self.directory / 'geoip.metadb').write_bytes(geoip_fixture())
        self.source = {
            'dns': {'nameserver': ['https://dns.example.invalid/query'],
                    'proxy-server-nameserver': ['https://private.example.invalid/query']},
            'ipv6': True, 'tcp-concurrent': True, 'sniffer': {'enable': False},
            'tun': {'enable': False, 'stack': 'mixed'},
            'rules': ['DOMAIN,first.invalid,DIRECT', 'GEOSITE,test@cn,出口',
                      'GEOIP,CN,DIRECT,no-resolve', 'MATCH,出口'],
        }

    def test_runtime_database_directory_must_belong_to_the_verified_core(self):
        process = {'ProcessId': 1234, 'ExecutablePath': str(geodata_module.APEX_CORE),
                   'CommandLine': f'"{geodata_module.APEX_CORE}" -f - -d "{self.directory}" -secret never-print'}
        invalid = [[], [process, process], {**process, 'ExecutablePath': 'unrelated.exe'},
                   {**process, 'ProcessId': 5678}, {**process, 'CommandLine': None},
                   {**process, 'CommandLine': 'ApexCore.exe -f -'}]
        for value in [process, *invalid]:
            encoded = base64.b64encode(json.dumps(value).encode()).decode()
            with self.subTest(valid=value == process), patch('utils.qingyunti_geodata.subprocess.run',
                    return_value=SimpleNamespace(stdout=encoded)):
                if value == process:
                    self.assertEqual(geodata_module.runtime_data_directory(1234), self.directory)
                else:
                    with self.assertRaises(ValueError) as error:
                        geodata_module.runtime_data_directory(1234)
                    self.assertNotIn('never-print', str(error.exception))

    def test_embeds_exact_database_entries_without_changing_dns_or_other_settings(self):
        original = copy.deepcopy(self.source)
        result = qingyunti_geodata(self.source, self.directory)
        self.assertEqual(self.source, original)
        for key in self.source.keys() - {'rules'}:
            self.assertEqual(result[key], self.source[key])
        self.assertEqual(len(result['rules']), len(self.source['rules']))
        self.assertEqual(result['rules'][0], self.source['rules'][0])
        self.assertEqual(result['rules'][-1], self.source['rules'][-1])
        site_name = result['rules'][1].split(',')[1]
        ip_name = result['rules'][2].split(',')[1]
        self.assertEqual(result['rules'][1], f'RULE-SET,{site_name},出口')
        self.assertEqual(result['rules'][2], f'RULE-SET,{ip_name},DIRECT,no-resolve')
        self.assertEqual(result['rule-providers'][site_name], {
            'type': 'inline', 'behavior': 'classical',
            'payload': ['DOMAIN-SUFFIX,example.cn', r'DOMAIN-REGEX,^a[1-5]\.example\.cn$'],
        })
        self.assertEqual(result['rule-providers'][ip_name], {
            'type': 'inline', 'behavior': 'ipcidr', 'payload': ['0.0.0.0/1'],
        })
        self.assertEqual(qingyunti_geodata(result, self.directory), result)

    def test_does_not_read_files_when_no_geodata_is_used(self):
        source = {**self.source, 'rules': ['MATCH,DIRECT']}
        self.assertEqual(qingyunti_geodata(source, self.directory / 'missing'), source)

    def test_missing_database_or_classification_fails_explicitly(self):
        for changes in ({'rules': ['GEOSITE,missing,DIRECT']},
                        {'rules': ['GEOIP,missing,DIRECT']}):
            with self.assertRaises(ValueError):
                qingyunti_geodata({**self.source, **changes}, self.directory)
        (self.directory / 'GeoSite.dat').unlink()
        with self.assertRaises(ValueError):
            qingyunti_geodata(self.source, self.directory)

    def test_does_not_silently_use_shared_geodata_for_dns_or_nested_rules(self):
        for changes in (
            {'dns': {'nameserver-policy': {'geosite:cn': ['system']}}},
            {'dns': {'fake-ip-filter': ['geosite:cn']}},
            {'dns': {'fake-ip-filter-mode': 'rule', 'fake-ip-filter': ['GEOSITE,cn,real-ip']}},
            {'dns': {'fallback-filter': {'geoip': False, 'geosite': ['cn']}}},
            {'rules': ['RULE-SET,local,DIRECT'], 'rule-providers': {
                'local': {'type': 'inline', 'behavior': 'classical', 'payload': ['GEOIP,CN']}}},
            {'dns': {'fallback': ['system']}},
            {'rules': ['AND,((GEOSITE,test),(NETWORK,TCP)),DIRECT']},
            {'rules': ['SRC-GEOIP,CN,DIRECT']},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                qingyunti_geodata({**self.source, **changes}, self.directory)


if __name__ == '__main__':
    unittest.main()
