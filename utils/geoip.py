"""Read country CIDRs from a local MaxMind database without changing shared data."""
from ipaddress import ip_network, IPv6Network, collapse_addresses
from pathlib import Path
import struct


MAX_DATABASE_SIZE = 64 * 1024 * 1024
METADATA_MARKER = b'\xab\xcd\xefMaxMind.com'


class CountryDatabase:
    def __init__(self, raw):
        self.raw = raw
        self.end = len(raw)
        self.data_start = 0
        marker = raw.rfind(METADATA_MARKER)
        if marker < 0:
            raise ValueError('Missing MMDB metadata')
        metadata, _ = self.value(marker + len(METADATA_MARKER))
        self.nodes = metadata['node_count']
        self.record_size = metadata['record_size']
        self.version = metadata['ip_version']
        if (metadata['binary_format_major_version'] != 2 or self.version not in (4, 6)
                or self.record_size not in (24, 28, 32) or self.nodes <= 0):
            raise ValueError('Unsupported MMDB metadata')
        self.node_size = self.record_size // 4
        self.tree_size = self.nodes * self.node_size
        self.data_start = self.tree_size + 16
        self.end = marker
        if self.data_start > marker or raw[self.tree_size:self.data_start] != bytes(16):
            raise ValueError('Invalid MMDB data separator')

    def value(self, offset, depth=0):
        if depth > 64 or not 0 <= offset < self.end:
            raise ValueError('Invalid MMDB data offset')
        control = self.raw[offset]
        kind, size, offset = control >> 5, control & 31, offset + 1
        if kind == 1:
            count = ((control >> 3) & 3) + 1
            raw, end = self.take(offset, count)
            pointer = int.from_bytes(raw, 'big')
            if count < 4:
                pointer += ((control & 7) << (count * 8)) + (0, 0, 2048, 526336)[count]
            return self.value(self.data_start + pointer, depth + 1)[0], end
        if kind == 0:
            raw, offset = self.take(offset, 1)
            kind = raw[0] + 7
        if size >= 29:
            raw, offset = self.take(offset, size - 28)
            size = (29, 285, 65821)[size - 29] + int.from_bytes(raw, 'big')
        if kind in (7, 11):
            return self.collection(kind, size, offset, depth)
        if kind == 14:
            if size not in (0, 1):
                raise ValueError('Invalid MMDB boolean')
            return bool(size), offset
        raw, end = self.take(offset, size)
        if kind == 2:
            return raw.decode('utf-8'), end
        if kind == 4:
            return raw, end
        if kind in (5, 6, 8, 9, 10):
            return int.from_bytes(raw, 'big', signed=kind == 8), end
        if kind in (3, 15):
            return struct.unpack('>d' if kind == 3 else '>f', raw)[0], end
        raise ValueError('Unsupported MMDB value')

    def take(self, offset, size):
        if offset < 0 or offset + size > self.end:
            raise ValueError('Truncated MMDB data')
        return self.raw[offset:offset + size], offset + size

    def collection(self, kind, size, offset, depth):
        if size > self.end - offset:
            raise ValueError('Invalid MMDB collection')
        items = []
        for _ in range(size):
            key, offset = self.value(offset, depth + 1)
            if kind == 7:
                value, offset = self.value(offset, depth + 1)
                items.append((key, value))
            else:
                items.append(key)
        return (dict(items) if kind == 7 else items), offset

    def children(self, node):
        start = node * self.node_size
        raw = self.raw[start:start + self.node_size]
        if self.record_size == 28:
            return (int.from_bytes(raw[:3], 'big') | ((raw[3] & 240) << 20),
                    ((raw[3] & 15) << 24) | int.from_bytes(raw[4:], 'big'))
        size = self.record_size // 8
        return int.from_bytes(raw[:size], 'big'), int.from_bytes(raw[size:], 'big')

    def networks(self, categories):
        result = {category: [] for category in categories}
        decoded = {}
        bits = 32 if self.version == 4 else 128
        stack = [(0, 0, 0)]
        while stack:
            node, address, prefix = stack.pop()
            if node == self.nodes:
                continue
            if node < self.nodes:
                if prefix >= bits:
                    raise ValueError('Invalid MMDB search tree')
                left, right = self.children(node)
                stack.extend(((right, address | (1 << (bits - prefix - 1)), prefix + 1),
                              (left, address, prefix + 1)))
                continue
            if node not in decoded:
                record = self.value(self.tree_size + node - self.nodes)[0]
                countries = record['country']['iso_code'] if isinstance(record, dict) else record
                countries = countries if isinstance(countries, list) else [countries]
                if not all(isinstance(country, str) for country in countries):
                    raise ValueError('Unsupported MMDB country record')
                decoded[node] = {country.upper() for country in countries}
            for category in categories:
                if category.upper() in decoded[node]:
                    network = (ip_network((address, prefix), strict=False) if bits == 32
                               else IPv6Network((address, prefix)))
                    result[category].append(network)
                    if bits == 128 and address < (1 << 32):
                        result[category].append(ip_network((address, max(0, prefix - 96)), strict=False))
        return {category: [str(network) for version in (4, 6)
                           for network in collapse_addresses(n for n in networks if n.version == version)]
                for category, networks in result.items()}


def geoip_networks(path, categories):
    requested = set(categories)
    if not requested:
        return {}
    try:
        path = Path(path)
        if path.stat().st_size > MAX_DATABASE_SIZE:
            raise ValueError('MMDB too large')
        result = CountryDatabase(path.read_bytes()).networks(requested)
        if any(not networks for networks in result.values()):
            raise ValueError('Missing country')
        return result
    except (OSError, ValueError, KeyError, TypeError, IndexError, UnicodeError, struct.error):
        raise ValueError('无法完整读取青云梯 GeoIP 数据库或缺少所需国家分类，请检查 geoip.metadb 后重新导出') from None
