import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.ip_checker import IPChecker


IP = '203.0.113.10'


def quality_result(source='ippure', **overrides):
    return {
        'ip': IP, 'source': source, 'pure_score': '27%', 'error': None,
        'full_string': '【🟢 机房|原生】', **overrides,
    }


class IPCheckerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.checker = IPChecker()
        self.checker.get_simple_ip = AsyncMock(return_value=IP)
        self.checker.ippure.check = AsyncMock(return_value=quality_result())

    async def test_ping0_ip_only_page_uses_fallback(self):
        session = AsyncMock()
        session.get.return_value = Mock(status_code=200, text=f"<script>window.ip = '{IP}';</script>")
        with patch('core.sources.ping0.AsyncSession') as factory:
            factory.return_value.__aenter__.return_value = session
            result = await self.checker.check_fast(source='ping0', fallback=True)
        self.assertEqual(result['pure_score'], '27%')
        self.assertEqual(result['source'], 'ippure')
        self.checker.ippure.check.assert_awaited_once()

    async def test_invalid_results_are_not_successful_or_cached(self):
        for invalid in (
            {'pure_score': '❓'}, {'pure_score': None}, {'pure_score': 'NaN%'},
            {'pure_score': '101%'}, {'pure_score': '-1%'}, {'pure_score': '27'},
            {'ip': '999.999.999.999'}, {'error': 'API error'},
        ):
            with self.subTest(invalid=invalid):
                self.checker.clear_cache()
                self.checker.ippure.check.return_value = quality_result(**invalid)
                result = await self.checker.check_fast(source='ippure', fallback=False)
                self.assertTrue(result['error'])
                self.assertEqual(self.checker.cache, {})

    async def test_valid_result_is_cached_for_the_same_policy(self):
        first = await self.checker.check_fast(source='ippure', fallback=False)
        cached = await self.checker.check_fast(source='ippure', fallback=False)
        self.assertEqual(cached, first)
        self.assertIsNot(cached, first)
        self.checker.ippure.check.assert_awaited_once()

    async def test_cache_does_not_override_selected_source(self):
        self.checker.ping0.check = AsyncMock(return_value=quality_result('ping0'))
        await self.checker.check_fast(source='ippure', fallback=False)
        result = await self.checker.check_fast(source='ping0', fallback=False)
        self.assertEqual(result['source'], 'ping0')
        self.checker.ping0.check.assert_awaited_once()

    async def test_cached_fallback_is_not_used_when_fallback_is_disabled(self):
        self.checker.ping0.check = AsyncMock(return_value=None)
        first = await self.checker.check_fast(source='ping0', fallback=True)
        cached = await self.checker.check_fast(source='ping0', fallback=True)
        strict = await self.checker.check_fast(source='ping0', fallback=False)
        self.assertEqual(first, cached)
        self.assertTrue(strict['error'])
        self.assertEqual(self.checker.ping0.check.await_count, 2)
        self.checker.ippure.check.assert_awaited_once()

    async def test_browser_and_fast_results_have_separate_caches(self):
        self.checker.browser_source.check = AsyncMock(return_value=quality_result(bot_score='20%'))
        browser = await self.checker.check_browser()
        fast = await self.checker.check_fast(source='ippure')
        cached_browser = await self.checker.check_browser()
        self.assertNotIn('bot_score', fast)
        self.assertEqual(browser, cached_browser)
        self.checker.ippure.check.assert_awaited_once()
        self.checker.browser_source.check.assert_awaited_once()

    async def test_browser_parse_failure_is_explicit_and_not_cached(self):
        self.checker.browser_source.check = AsyncMock(return_value=quality_result(
            ip='❓', pure_score='❓', bot_score='❓',
        ))
        result = await self.checker.check_browser()
        self.assertEqual(result['ip'], IP)
        self.assertTrue(result['error'])
        self.assertEqual(self.checker.cache, {})

    async def test_zero_risk_and_ipv6_are_valid(self):
        self.checker.ippure.check.return_value = quality_result(ip='2001:db8::1', pure_score='0%')
        result = await self.checker.check_fast(source='ippure', fallback=False)
        self.assertEqual(result['pure_score'], '0%')
        self.assertIsNone(result['error'])


if __name__ == '__main__':
    unittest.main()
