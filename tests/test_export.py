import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

from routers import api
from schemas import ExportRequest


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.original = self.yaml.load('''# subscription
defaults: &defaults
  type: ss
  server: example.invalid
  port: 443
  cipher: aes-128-gcm
  password: "012345"
proxies:
  - <<: *defaults
    name: good
  - <<: *defaults
    name: failed
group-defaults: &group-defaults
  type: select
proxy-groups:
  - <<: *group-defaults
    name: SELECT
    proxies: [good, failed, DIRECT]
rules: # leave unchanged
  - MATCH,SELECT
''')
        self.original_text = self.dump(self.original)
        self.nodes = [
            {
                'id': i,
                'original_name': proxy['name'],
                'name': proxy['name'] + '-checked',
                'status': 'failed' if i else 'success',
                'proxy_config': proxy,
            }
            for i, proxy in enumerate(self.original['proxies'])
        ]

    def dump(self, data):
        stream = io.StringIO()
        self.yaml.dump(data, stream)
        return stream.getvalue()

    def export(self, node_ids):
        with tempfile.TemporaryDirectory() as directory:
            real_open = open
            with patch.object(api.state, 'original_yaml', self.original), \
                 patch.object(api.state, 'nodes', self.nodes), \
                 patch('routers.api.open', side_effect=lambda path, *args, **kwargs:
                       real_open(Path(directory) / Path(path).name, *args, **kwargs)):
                result = asyncio.run(api.export_yaml(ExportRequest(node_ids=node_ids)))
                self.assertEqual(
                    (Path(directory) / result['filename']).read_text(encoding='utf-8'),
                    result['yaml'],
                )
        self.assertEqual(self.dump(self.original), self.original_text)
        return result['yaml']

    def test_export_skips_deepcopy_of_unchanged_yaml(self):
        with patch.object(CommentedSeq, '__deepcopy__',
                          side_effect=AssertionError('unchanged YAML must not be deep-copied')):
            output = self.export([1])
        exported = self.yaml.load(output)
        self.assertEqual([p['name'] for p in exported['proxies']], ['failed-checked'])
        self.assertEqual(exported['proxies'][0]['password'], '012345')
        self.assertEqual(exported['proxy-groups'][0]['proxies'], ['failed-checked', 'DIRECT'])
        self.assertEqual(exported['rules'], self.original['rules'])
        self.assertIn('# subscription', output)
        self.assertIn('# leave unchanged', output)

    def test_repeated_exports_do_not_accumulate_renames_or_remove_original_nodes(self):
        self.export([1])
        exported = self.yaml.load(self.export([0, 1]))
        self.assertEqual([p['name'] for p in exported['proxies']],
                         ['good-checked', 'failed-checked'])
        self.assertEqual(exported['proxy-groups'][0]['proxies'],
                         ['good-checked', 'failed-checked', 'DIRECT'])

    def test_config_without_proxy_groups_stays_without_proxy_groups(self):
        del self.original['proxy-groups']
        self.original_text = self.dump(self.original)
        self.assertNotIn('proxy-groups', self.yaml.load(self.export([1])))


if __name__ == '__main__':
    unittest.main()
