from pathlib import Path
import tempfile
import unittest

from utils.geoip import CountryDatabase, geoip_networks


def mmdb_value(value):
    if isinstance(value, list):
        return bytes([len(value), 4]) + b''.join(mmdb_value(item) for item in value)
    if isinstance(value, dict):
        return bytes([0xe0 | len(value)]) + b''.join(mmdb_value(k) + mmdb_value(v) for k, v in value.items())
    if isinstance(value, int):
        raw = value.to_bytes(max(1, (value.bit_length() + 7) // 8), 'big')
        return bytes([0xc0 | len(raw)]) + raw
    raw = value.encode('utf-8')
    return bytes([0x40 | len(raw)]) + raw


def geoip_fixture(record_size=24, ip_version=4, country=None):
    first = mmdb_value(country if country is not None else 'CN')
    data = first + mmdb_value('US')
    left, right = 17, 17 + len(first)
    if record_size == 28:
        tree = (left & 0xffffff).to_bytes(3, 'big') + bytes([((left >> 24) << 4) | (right >> 24)]) + (right & 0xffffff).to_bytes(3, 'big')
    else:
        size = record_size // 8
        tree = left.to_bytes(size, 'big') + right.to_bytes(size, 'big')
    metadata = {'node_count': 1, 'record_size': record_size, 'ip_version': ip_version,
                'binary_format_major_version': 2, 'database_type': 'test-country'}
    return tree + bytes(16) + data + b'\xab\xcd\xefMaxMind.com' + mmdb_value(metadata)


class GeoipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'geoip.metadb'

    def test_reads_all_record_sizes_and_country_record_shapes(self):
        for size in (24, 28, 32):
            for country in ('CN', ['CN', 'TEST'], {'country': {'iso_code': 'CN'}}):
                with self.subTest(size=size, country=country):
                    self.path.write_bytes(geoip_fixture(size, country=country))
                    self.assertEqual(geoip_networks(self.path, {'CN', 'us'}),
                                     {'CN': ['0.0.0.0/1'], 'us': ['128.0.0.0/1']})
        self.assertEqual(geoip_networks(self.path, set()), {})

    def test_28_bit_record_high_nibbles_follow_the_mmdb_layout(self):
        raw = geoip_fixture(28)
        database = CountryDatabase(bytes.fromhex('23456719876543') + raw[7:])
        self.assertEqual(database.children(0), (0x1234567, 0x9876543))

    def test_expands_ipv6_and_ipv4_lookup_prefix(self):
        self.path.write_bytes(geoip_fixture(ip_version=6))
        result = geoip_networks(self.path, {'CN'})
        self.assertIn('::/1', result['CN'])
        self.assertIn('0.0.0.0/0', result['CN'])

    def test_rejects_missing_corrupt_empty_or_unknown_categories(self):
        for raw in (b'', b'not a database', geoip_fixture()[:-1], geoip_fixture()[:5]):
            self.path.write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                geoip_networks(self.path, {'CN'})
        self.path.write_bytes(geoip_fixture())
        with self.assertRaises(ValueError):
            geoip_networks(self.path, {'missing'})
        with self.assertRaises(ValueError):
            geoip_networks(self.path.with_name('missing.metadb'), {'CN'})

    def test_rejects_cycles_and_out_of_bounds_data_records(self):
        for record in (0, 0xffffff):
            raw = geoip_fixture()
            self.path.write_bytes(record.to_bytes(3, 'big') + raw[3:])
            with self.subTest(record=record), self.assertRaises(ValueError):
                geoip_networks(self.path, {'CN'})


if __name__ == '__main__':
    unittest.main()
