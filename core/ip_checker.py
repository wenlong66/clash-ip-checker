import asyncio
import re
import aiohttp
from ipaddress import ip_address
from typing import Optional, Dict

# Strategies
from .sources.ping0 import Ping0Source
from .sources.ippure import IPPureSource
from .sources.browser import BrowserSource

class IPChecker:
    def __init__(self, headless=True):
        self._headless = headless
        
        # Components
        self.ping0 = Ping0Source()
        self.ippure = IPPureSource()
        self.browser_source = BrowserSource(headless=headless)
        
        self.cache = {} # Map (mode, source, fallback, IP) -> Result Dict

    def clear_cache(self):
        """Clears the IP result cache."""
        self.cache = {}
        print("[IPChecker] Cache cleared.")

    @staticmethod
    def _is_usable_result(result):
        if not result or result.get("error"):
            return False
        ip = result.get("ip")
        score = result.get("pure_score")
        if not isinstance(ip, str) or not isinstance(score, str) or not score.endswith("%"):
            return False
        try:
            ip_address(ip)
            return 0 <= float(score[:-1]) <= 100
        except ValueError:
            return False

    @property
    def headless(self):
        return self._headless

    @headless.setter
    def headless(self, value):
        self._headless = value
        self.browser_source.headless = value

    async def start(self):
        await self.browser_source.start()

    async def stop(self):
        await self.browser_source.stop()

    async def get_simple_ip(self, proxy=None):
        """Fast IPv4 check for caching."""
        urls = ["http://api.ipify.org", "http://v4.ident.me"]
        for url in urls:
            try:
                # User modified timeout to 3s
                timeout = aiohttp.ClientTimeout(total=3)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, proxy=proxy) as resp:
                        if resp.status == 200:
                            ip = (await resp.text()).strip()
                            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                                return ip
            except Exception:
                continue 
        return None

    # --- Main Interface ---

    async def check_browser(self, url="https://ippure.com/", proxy=None, timeout=20000):
        """Full browser check"""
        
        # 1. Cleaner Fast IP & Cache Logic
        current_ip = await self.get_simple_ip(proxy)
        cache_key = ("browser", "ippure", False, current_ip)
        if current_ip and cache_key in self.cache:
            print(f"     [Cache Hit] {current_ip}")
            return self.cache[cache_key].copy()
        
        if current_ip:
            print(f"     [New IP] {current_ip}")
        else:
            print("     [Warning] Fast IP check failed. Scanning with browser...")

        # 2. Delegate to Browser Source
        result = await self.browser_source.check(proxy)
        
        # Inject IP if browser failed to find it but simple check passed
        if result["ip"] == "❓" and current_ip:
            result = {**result, "ip": current_ip}

        if not self._is_usable_result(result):
            return {
                **result,
                "error": result.get("error") or "Browser returned no valid IP quality score",
                "full_string": "【❌ Check Failed】",
            }

        cache_key = ("browser", "ippure", False, result["ip"])
        self.cache = {**self.cache, cache_key: result.copy()}
        return result

    async def check_fast(self, proxy=None, source="ping0", fallback=True):
        """
        Fast mode: Prioritizes source (ping0/ippure), falls back if enabled.
        """
        try:
            # Hard timeout of 20 seconds for entire check
            return await asyncio.wait_for(
                self._check_fast_impl(proxy, source, fallback),
                timeout=15
            )
        except asyncio.TimeoutError:
            print(f"     [check_fast] Total timeout exceeded")
            return {
                "pure_emoji": "❓", "shared_emoji": "❓", "ip_attr": "❓", "ip_src": "❓",
                "pure_score": "❓", "shared_users": "N/A", "full_string": "【⏱️ Timeout】", 
                "ip": "❓", "error": "Timeout", "source": "timeout"
            }
    
    async def _check_fast_impl(self, proxy=None, source="ping0", fallback=True):
        """Internal implementation of check_fast with prioritization"""
        try:
            fast_ip = await self.get_simple_ip(proxy)
        except Exception:
            print("     [Check] Fast IP lookup failed; trying quality sources")
            fast_ip = None
        cache_key = ("fast", source, fallback, fast_ip)
        if fast_ip and cache_key in self.cache:
            return self.cache[cache_key].copy()

        sources = (self.ping0, self.ippure) if source == "ping0" else (self.ippure, self.ping0)
        for index, check_source in enumerate(sources if fallback else sources[:1]):
            if index:
                print(f"     [Check] {source} failed, falling back...")
            result = await check_source.check(proxy)
            if self._is_usable_result(result):
                cache_key = ("fast", source, fallback, result["ip"])
                self.cache = {**self.cache, cache_key: result.copy()}
                return result
                
        # 3. Failed
        return {
            "pure_emoji": "❓", "shared_emoji": "❓", "ip_attr": "❓", "ip_src": "❓",
            "pure_score": "❓", "shared_users": "N/A", "full_string": "【❌ Check Failed】", 
            "ip": "❓", "error": f"All sources failed (Primary: {source})", "source": "failed"
        }
