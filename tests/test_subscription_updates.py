import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from ruamel.yaml import YAML

from routers import api, failover, qingyunti


class SubscriptionUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        (self.root / 'exports').mkdir()
        self.items = []
        self.yaml = YAML()
        self.write_profiles()
        for mocked in (
            patch.object(failover, 'profile_directory', return_value=self.root),
            patch.object(api.state, 'nodes', [{'id': 0, 'original_name': 'A', 'name': 'A',
                         'proxy_config': {'name': 'A', 'type': 'ss', 'server': 'example.invalid'}}]),
            patch.object(api.state, 'original_yaml', {}),
            patch.object(api.state, 'task_id', '12345678-task'),
            patch.object(qingyunti.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, 'proxies: [{name: A, type: ss, server: example.invalid}]', '')),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)
        app = FastAPI()
        for router in (api.router, failover.router, qingyunti.router):
            app.include_router(router)
        app.mount('/exports', StaticFiles(directory='exports'))
        self.client = self.client_for(app)

    def client_for(self, app):
        return TestClient(app, base_url='http://127.0.0.1:18080', client=('127.0.0.1', 54321))

    def write_profiles(self):
        stream = io.StringIO()
        self.yaml.dump({'items': self.items}, stream)
        (self.root / 'profiles.yaml').write_text(stream.getvalue(), encoding='utf-8')

    def export(self, kind, target=''):
        if kind == 'checked':
            return self.client.post('/api/export', json={'node_ids': [0], 'target_profile_id': target})
        return self.client.post('/api/qingyunti/export', params={'target_profile_id': target})

    def imported(self, kind):
        response = self.export(kind)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.items.append({'uid': kind, 'type': 'remote', 'name': kind, 'file': 'unused.yaml',
                           'url': 'http://127.0.0.1:18080' + data['url']})
        self.write_profiles()
        return data

    def test_new_configs_have_independent_durable_urls_and_updates_reuse_them(self):
        for kind in ('checked', 'qingyunti'):
            with self.subTest(kind=kind):
                api.state.nodes[0]['name'] = 'A'
                qingyunti.subprocess.run.return_value.stdout = 'proxies: [{name: A, type: ss, server: example.invalid}]'
                first = self.imported(kind)
                second = self.export(kind).json()
                self.assertNotEqual(first['url'], second['url'])
                self.assertEqual(self.client_for(self.client.app).get(first['url']).text, first['yaml'])
                api.state.nodes[0]['name'] = 'B'
                qingyunti.subprocess.run.return_value.stdout = 'proxies: [{name: B, type: ss, server: example.invalid}]'
                updated = self.export(kind, kind)
                self.assertEqual(updated.status_code, 200, updated.text)
                self.assertEqual(updated.json()['url'], first['url'])
                self.assertEqual(updated.json()['updated_profile'], kind)
                self.assertNotEqual(updated.json()['yaml'], first['yaml'])
                self.assertIn('B', self.client.get(first['url']).text)
                self.assertEqual(self.client.get(second['url']).text, second['yaml'])
                listing = self.client.get('/api/failover/profiles', params={'kind': kind}).json()['profiles']
                targets = [item['id'] for item in listing if item.get('export_filename')]
                self.assertEqual(targets, [kind])

    def test_wrong_kind_missing_and_foreign_targets_cannot_overwrite_exports(self):
        old = self.imported('checked')
        self.assertEqual(self.export('qingyunti', 'checked').status_code, 400)
        self.imported('qingyunti')
        self.assertEqual(self.export('checked', 'qingyunti').status_code, 400)
        for kind in ('checked', 'qingyunti'):
            self.assertEqual(self.export(kind, 'missing').status_code, 400)
        self.items[0]['url'] = 'https://example.invalid' + old['url']
        self.write_profiles()
        self.assertEqual(self.export('checked', 'checked').status_code, 400)
        self.assertEqual(self.client.get(old['url']).text, old['yaml'])

    def test_legacy_checked_links_can_be_updated_but_missing_exports_are_rejected(self):
        old = self.imported('checked')
        legacy = 'clash_checked_12345678.yaml'
        (self.root / 'exports' / old['filename']).rename(self.root / 'exports' / legacy)
        self.items[0]['url'] = 'http://localhost:18080/exports/' + legacy + '?flag=meta'
        self.write_profiles()
        updated = self.export('checked', 'checked')
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['url'], '/exports/' + legacy)
        (self.root / 'exports' / legacy).unlink()
        self.assertEqual(self.export('checked', 'checked').status_code, 400)

    def test_failed_save_preserves_previous_content_and_private_exports_stay_local(self):
        for kind in ('checked', 'qingyunti'):
            old = self.imported(kind)
            with patch.object(Path, 'replace', side_effect=OSError('write failed')):
                response = self.export(kind, kind)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(self.client.get(old['url']).text, old['yaml'])
        private = self.items[-1]['url'].split('http://127.0.0.1:18080')[1]
        self.assertEqual(self.client.get(private, headers={'host': 'example.invalid'}).status_code, 403)
        self.assertEqual(self.client.get('/exports/' + old['filename']).status_code, 404)
        self.assertEqual(list(self.root.rglob('*.tmp')), [])
