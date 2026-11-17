import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import api
from state import AppState


YAML_CONTENT = 'proxies: [{name: A}, {name: 公告}, {name: B}, {name: C}]'
CONFIG = {'skip_keywords_str': '公告', 'source': 'ippure'}


class SelectedCheckAPITests(unittest.TestCase):
    def setUp(self):
        self.state = AppState()
        self.state_patch = patch.object(api, 'state', self.state)
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.worker = self.enterContext(patch.object(api, '_run_check', new_callable=AsyncMock))
        app = FastAPI()
        app.include_router(api.router)
        self.client = self.enterContext(TestClient(app))

    def prepare(self):
        response = self.client.post('/api/prepare', json={'yaml_content': YAML_CONTENT, 'config': CONFIG})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['nodes']

    def start(self, node_ids, **overrides):
        return self.client.post('/api/start', json={
            'yaml_content': YAML_CONTENT, 'config': CONFIG, 'node_ids': node_ids, **overrides,
        })

    def test_load_only_creates_list_without_starting_checks(self):
        nodes = self.prepare()
        self.assertEqual([node['original_name'] for node in nodes], ['A', 'B', 'C'])
        self.assertEqual([node['id'] for node in nodes], [0, 2, 3])
        self.assertFalse(self.state.is_running)
        self.worker.assert_not_called()
        self.assertEqual(len(self.state.original_yaml['proxies']), 4)

    def test_selected_start_keeps_unselected_results_and_ids(self):
        nodes = self.prepare()
        untouched = {**nodes[0], 'name': 'A-checked', 'risk': '12%', 'status': '✅'}
        self.state.nodes = [untouched, *nodes[1:]]
        response = self.start([3, 2])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['total'], 2)
        checked, config = self.worker.call_args.args
        self.assertEqual([node['id'] for node in checked], [2, 3])
        self.assertEqual(config, CONFIG)
        self.assertEqual(self.state.nodes[0], untouched)
        self.assertEqual([node['id'] for node in self.state.nodes], [0, 2, 3])

    def test_empty_missing_duplicate_and_unknown_selections_are_rejected(self):
        nodes = self.prepare()
        for ids in ([], [0, 0], [999], [1], [-1]):
            with self.subTest(ids=ids):
                self.assertIn(self.start(ids).status_code, (400, 422))
                self.assertEqual(self.state.nodes, nodes)
                self.assertFalse(self.state.is_running)
        missing = self.client.post('/api/start', json={'yaml_content': YAML_CONTENT})
        self.assertEqual(missing.status_code, 422)
        self.worker.assert_not_called()

    def test_edited_yaml_requires_reloading_before_checking(self):
        nodes = self.prepare()
        response = self.start([0], yaml_content='proxies: [{name: Different node}]')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.state.nodes, nodes)
        self.worker.assert_not_called()

    def test_loading_and_starting_wait_for_a_stopping_worker(self):
        self.prepare()
        self.state.check_task = Mock(done=Mock(return_value=False))
        self.assertEqual(self.start([0]).status_code, 409)
        response = self.client.post('/api/prepare', json={'yaml_content': YAML_CONTENT})
        self.assertEqual(response.status_code, 409)
        self.worker.assert_not_called()

    def test_bad_yaml_does_not_destroy_the_loaded_list(self):
        nodes = self.prepare()
        for text in ('[]', 'proxies: [invalid]', 'proxies: []', 'proxies: ['):
            with self.subTest(text=text):
                response = self.client.post('/api/prepare', json={'yaml_content': text})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.state.nodes, nodes)


class SelectedCheckWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_contiguous_selection_updates_only_selected_rows(self):
        for outcome in ('success', 'switch_failed', 'check_failed'):
            with self.subTest(outcome=outcome):
                state = AppState()
                state.is_running = True
                nodes = [
                    {'id': index, 'name': name + '-old', 'original_name': name,
                     'proxy_config': {'name': name}, 'risk': '12%'}
                    for index, name in ((0, 'A'), (2, 'B'), (3, 'C'))
                ]
                state.nodes = nodes
                state.checker = Mock(check_fast=AsyncMock(
                    return_value={'source': 'ippure', 'pure_score': '27%', 'error': None},
                    side_effect=RuntimeError('failed') if outcome == 'check_failed' else None,
                ))
                controller = Mock(
                    set_mode=AsyncMock(return_value=True), get_running_port=AsyncMock(return_value=7890),
                    switch_proxy=AsyncMock(return_value=outcome != 'switch_failed'),
                )
                with patch.object(api, 'state', state), patch.object(api, 'ClashController', return_value=controller), \
                        patch('routers.api.asyncio.sleep', new_callable=AsyncMock):
                    await api._run_check(nodes[1:], CONFIG)
                self.assertEqual(state.nodes[0], nodes[0])
                self.assertEqual([node['id'] for node in state.nodes], [0, 2, 3])
                self.assertEqual(controller.switch_proxy.await_args_list, [call('GLOBAL', 'B'), call('GLOBAL', 'C')])
                updates = [event for event in state.events if event['type'] == 'progress']
                self.assertEqual([event['node']['id'] for event in updates], [2, 3])
                self.assertEqual([event['progress'] for event in updates], [1, 2])
                self.assertEqual(state.progress, 2)
                self.assertEqual(state.events[-1], {'type': 'complete', 'total': 2})


if __name__ == '__main__':
    unittest.main()
