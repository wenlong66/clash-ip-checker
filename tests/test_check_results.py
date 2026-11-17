import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from routers.api import _run_check, recheck_node
from schemas import RecheckRequest
from web import lifespan


class CheckResultTests(unittest.IsolatedAsyncioTestCase):
    async def check_node(self, result, config, recheck, name='Test node'):
        proxy = {'name': name}
        node = {'id': 0, 'name': proxy['name'], 'original_name': proxy['name'], 'proxy_config': proxy}
        checker = Mock(check_fast=AsyncMock(return_value=result), check_browser=AsyncMock(return_value=result))
        state = SimpleNamespace(checker=checker, nodes=[node], events=[], is_running=not recheck)
        controller = Mock(
            set_mode=AsyncMock(return_value=True),
            switch_proxy=AsyncMock(return_value=True),
            get_running_port=AsyncMock(return_value=7890),
        )
        with patch('routers.api.state', state), patch('routers.api.ClashController', return_value=controller), \
                patch('routers.api.asyncio.sleep', new_callable=AsyncMock):
            if recheck:
                await recheck_node(0, RecheckRequest(config=config))
            else:
                await _run_check([node], config)
        return state.nodes[0]

    async def test_flag_named_nodes_work_with_gbk_output(self):
        name = '🇦🇺 测试节点'
        result = {'source': 'ippure', 'pure_score': '0%', 'error': None}
        for recheck in (False, True):
            with self.subTest(recheck=recheck), \
                    io.TextIOWrapper(io.BytesIO(), encoding='gbk', errors='strict') as output, \
                    io.TextIOWrapper(io.BytesIO(), encoding='gbk', errors='strict') as errors:
                with patch('sys.stdout', output), patch('sys.stderr', errors), \
                        patch('web.state.checker.stop', new_callable=AsyncMock):
                    async with lifespan(None):
                        node = await self.check_node(result, {'source': 'ippure'}, recheck, name)
                        self.assertEqual(node['status'], '✅')
                        self.assertEqual(node['risk'], '0%')
                        self.assertEqual(node['original_name'], name)
                        print(name, file=errors)

    async def test_batch_exceptions_publish_failed_node_and_progress(self):
        proxy = {'name': 'Test node'}
        checker = Mock(check_fast=AsyncMock(side_effect=RuntimeError('Source unavailable')))
        node = {'id': 0, 'name': proxy['name'], 'proxy_config': proxy}
        state = SimpleNamespace(checker=checker, nodes=[node], events=[], is_running=True)
        controller = Mock(
            set_mode=AsyncMock(return_value=True), switch_proxy=AsyncMock(return_value=True),
            get_running_port=AsyncMock(return_value=7890),
        )
        with patch('routers.api.state', state), patch('routers.api.ClashController', return_value=controller), \
                patch('routers.api.asyncio.sleep', new_callable=AsyncMock):
            await _run_check([node], {})
        updates = [event for event in state.events if event['type'] == 'progress']
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]['node']['error'], 'Source unavailable')
        self.assertEqual(updates[0]['progress'], 1)
        self.assertEqual(state.progress, 1)
        self.assertFalse(state.is_running)

    async def test_selected_source_and_browser_results_are_successful(self):
        for recheck in (False, True):
            for config, source in (
                ({'source': 'ping0'}, 'ping0'),
                ({'source': 'ippure'}, 'ippure'),
                ({'source': 'ping0', 'fast_mode': False}, 'ippure'),
            ):
                with self.subTest(recheck=recheck, config=config):
                    node = await self.check_node({'source': source, 'pure_score': '0%', 'error': None}, config, recheck)
                    self.assertEqual(node['status'], '✅')

    async def test_fallback_results_are_degraded_in_either_direction(self):
        for recheck in (False, True):
            for primary, actual in (('ping0', 'ippure'), ('ippure', 'ping0')):
                with self.subTest(recheck=recheck, primary=primary):
                    node = await self.check_node(
                        {'source': actual, 'pure_score': '27%', 'error': None}, {'source': primary}, recheck,
                    )
                    self.assertEqual(node['status'], '⚠️ 降级')

    async def test_failed_checks_keep_the_error_and_are_not_degraded(self):
        for recheck in (False, True):
            with self.subTest(recheck=recheck):
                node = await self.check_node(
                    {'source': 'failed', 'pure_score': '❓', 'error': 'All sources failed'}, {}, recheck,
                )
                self.assertEqual(node['status'], '❌ 失败')
                self.assertEqual(node['error'], 'All sources failed')


if __name__ == '__main__':
    unittest.main()
