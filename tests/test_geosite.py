from pathlib import Path
import tempfile
import unittest

from utils.geosite import geosite_domains


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode('utf-8')
    return varint((number << 3) | 2) + varint(len(value)) + value


def geosite_fixture():
    cn = field(3, field(1, 'cn') + field(2, 1))
    disabled = field(3, field(1, 'disabled') + field(2, 0))
    domains = [field(1, 2) + field(2, 'example.cn') + cn,
               field(1, 3) + field(2, 'www.example.com') + disabled,
               field(1, 1) + field(2, r'^a[1-5]\.example\.cn$') + cn,
               field(2, 'keyword')]
    return field(1, field(1, 'TEST') + b''.join(field(2, domain) for domain in domains))


class GeositeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'GeoSite.dat'
        self.path.write_bytes(geosite_fixture())

    def test_reads_domain_types_and_boolean_attributes(self):
        result = geosite_domains(self.path, ['test', 'test@cn', 'test@!cn', 'test@!disabled'])
        self.assertEqual(len(result['test']), 4)
        self.assertEqual(result['test@cn'], [(2, 'example.cn'), (1, r'^a[1-5]\.example\.cn$')])
        self.assertEqual(result['test@!cn'], [(3, 'www.example.com'), (0, 'keyword')])
        self.assertEqual(result['test'], result['test@!disabled'])
        self.assertEqual(geosite_domains(self.path, []), {})

    def test_missing_corrupt_or_incomplete_data_is_not_silently_ignored(self):
        for raw in (b'\x0a\xff', b'\x0a\x10short', b'\x0f', b''):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                geosite_domains(self.path, ['test'])
        self.path.write_bytes(geosite_fixture())
        for category in ('missing', 'test@missing'):
            with self.assertRaises(ValueError):
                geosite_domains(self.path, [category])
        with self.assertRaises(ValueError):
            geosite_domains(self.path.with_name('missing.dat'), ['test'])


if __name__ == '__main__':
    unittest.main()
