import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from ruamel.yaml import YAML

from routers import failover


class FailoverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous_cwd)
        (self.root / 'profiles').mkdir()
        self.yaml = YAML()
        self.items = [
            {'uid': 'a', 'type': 'remote', 'name': '订阅 A', 'file': 'a.yaml', 'url': 'https://example.invalid/private-token'},
            {'uid': 'b', 'type': 'local', 'name': '订阅 B', 'file': 'b.yaml'},
            {'uid': 'script', 'type': 'script', 'file': 'script.js'},
        ]
        self.write('profiles.yaml', {'items': self.items})
        for profile in ('a', 'b'):
            self.write(f'profiles/{profile}.yaml', {
                'secret': 'controller-secret',
                'proxies': [{'name': '日本 01', 'type': 'ss', 'server': 'example.invalid', 'port': 443,
                             'cipher': 'aes-128-gcm', 'password': f'password-{profile}', 'udp': True}],
                'proxy-groups': [{'name': 'OLD', 'type': 'select', 'proxies': ['missing-node']}],
                'rules': ['MATCH,OLD'],
            })
        directory_patch = patch.object(failover, 'profile_directory', return_value=self.root)
        directory_patch.start()
        self.addCleanup(directory_patch.stop)
        app = FastAPI()
        app.include_router(failover.router)
        self.client = TestClient(app, base_url='http://127.0.0.1:18080', client=('127.0.0.1', 54321))
        self.request = {'primary': {'profile_id': 'a', 'node_name': '日本 01'},
                        'backup': {'profile_id': 'b', 'node_name': '日本 01'}, 'interval': 60}

    def write(self, filename, data):
        stream = io.StringIO()
        self.yaml.dump(data, stream)
        (self.root / filename).write_text(stream.getvalue(), encoding='utf-8')

    def test_listing_only_returns_profile_and_node_names(self):
        self.items.append({'uid': 'broken', 'type': 'local', 'name': '损坏订阅', 'file': 'missing.yaml'})
        self.write('profiles.yaml', {'items': self.items})
        response = self.client.get('/api/failover/profiles')
        self.assertEqual(response.status_code, 200)
        profiles = response.json()['profiles']
        self.assertEqual(profiles[0], {'id': 'a', 'name': '订阅 A', 'nodes': ['日本 01']})
        self.assertEqual(len(profiles), 3)
        self.assertIn('error', profiles[2])
        self.assertNotIn('password', response.text)
        self.assertNotIn('private-token', response.text)

    def test_cross_subscription_duplicate_names_generate_complete_independent_config(self):
        originals = {p: p.read_bytes() for p in (self.root / 'profiles').iterdir()}
        response = self.client.post('/api/failover/export', json=self.request)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        config = self.yaml.load(result['yaml'])
        self.assertEqual([node['password'] for node in config['proxies']], ['password-a', 'password-b'])
        names = [node['name'] for node in config['proxies']]
        self.assertEqual(len(set(names)), 2)
        groups = config['proxy-groups']
        self.assertEqual(groups[0]['proxies'], ['主用节点', '备用节点'])
        self.assertEqual(groups[0]['interval'], 60)
        self.assertEqual(groups[1]['proxies'], names[:1])
        self.assertEqual(groups[2]['proxies'], names[1:])
        self.assertEqual(config['rules'][-1], 'MATCH,主备切换')
        self.assertIn('GEOIP,CN,DIRECT', config['rules'])
        providers = config['rule-providers']
        rule_sets = [rule.split(',')[1] for rule in config['rules'] if rule.startswith('RULE-SET,')]
        self.assertEqual(set(rule_sets), set(providers))
        self.assertEqual(len(providers), 11)
        for name, provider in providers.items():
            self.assertEqual(provider['type'], 'http')
            self.assertEqual(provider['interval'], 86400)
            self.assertEqual(provider['url'], f'https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/{name}.txt')
            self.assertEqual(provider['behavior'], 'classical' if name == 'applications'
                             else 'ipcidr' if name.endswith('cidr') else 'domain')
        rules = config['rules']
        self.assertLess(rules.index('RULE-SET,private,DIRECT'), rules.index('RULE-SET,reject,REJECT'))
        self.assertLess(rules.index('RULE-SET,reject,REJECT'), rules.index('RULE-SET,direct,DIRECT'))
        for name in ('google', 'proxy', 'telegramcidr'):
            self.assertIn(f'RULE-SET,{name},主备切换', rules)
        for name in ('applications', 'private', 'icloud', 'apple', 'direct', 'lancidr', 'cncidr'):
            self.assertIn(f'RULE-SET,{name},DIRECT', rules)
        self.assertNotIn('secret', config)
        self.assertNotIn('OLD', result['yaml'])
        self.assertEqual((self.root / 'exports' / result['filename']).read_text(encoding='utf-8'), result['yaml'])
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)

    def test_same_selection_stale_selection_and_invalid_interval_are_rejected(self):
        self.request['backup'] = self.request['primary'].copy()
        self.assertEqual(self.client.post('/api/failover/export', json=self.request).status_code, 400)
        self.request['backup'] = {'profile_id': '../outside', 'node_name': '日本 01'}
        self.assertEqual(self.client.post('/api/failover/export', json=self.request).status_code, 400)
        self.request['backup'] = {'profile_id': 'b', 'node_name': 'removed-node'}
        self.assertEqual(self.client.post('/api/failover/export', json=self.request).status_code, 400)
        self.request['interval'] = 0
        self.assertEqual(self.client.post('/api/failover/export', json=self.request).status_code, 422)
        self.assertFalse((self.root / 'exports').exists())

    def imported_export(self):
        result = self.client.post('/api/failover/export', json=self.request).json()
        self.items.append({'uid': 'generated', 'type': 'remote', 'name': '已有主备',
                           'file': 'generated.yaml', 'url': 'http://127.0.0.1:18080' + result['url']})
        self.write('profiles.yaml', {'items': self.items})
        self.write('profiles/generated.yaml', self.yaml.load(result['yaml']))
        return result

    def test_second_backup_is_optional_and_keeps_priority_order(self):
        original = self.yaml.load((self.root / 'profiles/b.yaml').read_text(encoding='utf-8'))
        original['proxies'].append({**original['proxies'][0], 'name': '日本 02'})
        self.write('profiles/b.yaml', original)
        self.request['backup2'] = {'profile_id': 'b', 'node_name': '日本 02'}
        response = self.client.post('/api/failover/export', json=self.request)
        self.assertEqual(response.status_code, 200, response.text)
        config = self.yaml.load(response.json()['yaml'])
        self.assertEqual(len(config['proxies']), 3)
        self.assertEqual(config['proxy-groups'][0]['proxies'], ['主用节点', '备用节点', '备用节点2'])
        self.assertEqual(config['proxy-groups'][3]['proxies'], [config['proxies'][2]['name']])
        self.request['backup2'] = self.request['backup'].copy()
        self.assertEqual(self.client.post('/api/failover/export', json=self.request).status_code, 400)

    def test_update_reuses_the_imported_url_without_modifying_clash_files(self):
        old = self.imported_export()
        self.items[-1]['url'] += '?flag=meta'
        self.write('profiles.yaml', {'items': self.items})
        originals = {path: path.read_bytes() for path in (self.root / 'profiles').iterdir()}
        metadata = (self.root / 'profiles.yaml').read_bytes()
        listing = self.client.get('/api/failover/profiles').json()['profiles']
        self.assertEqual(listing[-1]['export_filename'], old['filename'])
        self.request.update(target_profile_id='generated', interval=300)
        response = self.client.post('/api/failover/export', json=self.request)
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertEqual(updated['url'], old['url'])
        self.assertEqual(updated['updated_profile'], '已有主备')
        saved = self.yaml.load((self.root / 'exports' / old['filename']).read_text(encoding='utf-8'))
        self.assertEqual(saved['proxy-groups'][0]['interval'], 300)
        self.assertEqual(len(list((self.root / 'exports').iterdir())), 1)
        self.assertEqual((self.root / 'profiles.yaml').read_bytes(), metadata)
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_only_generated_local_exports_can_be_update_targets(self):
        old = self.imported_export()
        self.request['target_profile_id'] = 'generated'
        for url in ('https://example.invalid' + old['url'],
                    'http://127.0.0.1:18081' + old['url'],
                    'http://127.0.0.1:18080/exports/../profiles/a.yaml',
                    'http://127.0.0.1:18080/exports/clash_checked_old.yaml'):
            self.items[-1]['url'] = url
            self.write('profiles.yaml', {'items': self.items})
            response = self.client.post('/api/failover/export', json=self.request)
            self.assertEqual(response.status_code, 400, url)
        self.assertEqual((self.root / 'exports' / old['filename']).read_text(encoding='utf-8'), old['yaml'])

    def test_failed_update_preserves_previous_export(self):
        old = self.imported_export()
        self.request['target_profile_id'] = 'generated'
        with patch.object(Path, 'replace', side_effect=OSError('cannot replace')):
            response = self.client.post('/api/failover/export', json=self.request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual((self.root / 'exports' / old['filename']).read_text(encoding='utf-8'), old['yaml'])
        self.assertEqual(list((self.root / 'exports').glob('*.tmp')), [])

    def test_metadata_cannot_read_outside_profile_directory(self):
        self.items[0]['file'] = '../profiles.yaml'
        self.write('profiles.yaml', {'items': self.items})
        self.assertIn('error', self.client.get('/api/failover/profiles').json()['profiles'][0])
        self.assertEqual(self.client.post('/api/failover/export', json=self.request).status_code, 400)

    def test_chained_nodes_are_rejected_instead_of_exporting_broken_dependencies(self):
        self.write('profiles/a.yaml', {'proxies': [
            {'name': '日本 01', 'type': 'http', 'server': 'example.invalid', 'port': 443, 'dialer-proxy': 'upstream'}]})
        response = self.client.post('/api/failover/export', json=self.request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('链式代理', response.json()['detail'])

    def test_foreign_origins_and_hosts_cannot_read_local_subscriptions(self):
        self.assertEqual(self.client.get('/api/failover/profiles', headers={'Host': 'attacker.invalid'}).status_code, 403)
        self.assertEqual(self.client.get('/api/failover/profiles', headers={'Origin': 'https://attacker.invalid'}).status_code, 403)
        self.assertEqual(self.client.post('/api/failover/export', json=self.request,
                                         headers={'Origin': 'https://attacker.invalid'}).status_code, 403)
        self.assertEqual(self.client.get('/api/failover/profiles',
                                        headers={'Origin': 'http://127.0.0.1:18080'}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
