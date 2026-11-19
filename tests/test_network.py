import subprocess
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from utils import network


class NetworkTests(unittest.TestCase):
    def setUp(self):
        network.lan_ip.cache_clear()
        self.addCleanup(network.lan_ip.cache_clear)

    def request(self, host='127.0.0.1', client='127.0.0.1', path='/'):
        return Request({'type': 'http', 'scheme': 'http', 'path': path,
                        'headers': [(b'host', f'{host}:18080'.encode())],
                        'server': (host, 18080), 'client': (client, 12345)})

    def test_lan_ip_uses_physical_adapter_and_is_cached(self):
        with patch.object(network.os, 'name', 'nt'), \
                patch.object(network.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '10.12.64.8\n')) as run:
            self.assertEqual(network.lan_ip(), '10.12.64.8')
            self.assertEqual(network.lan_ip(), '10.12.64.8')
            run.assert_called_once()
            self.assertIn('HardwareInterface', run.call_args.args[0][-1])

    def test_invalid_or_unavailable_lan_ip_is_not_replaced_with_loopback(self):
        for result in ('127.0.0.1', '169.254.1.1', '8.8.8.8', 'not-an-ip', ''):
            with self.subTest(result=result), patch.object(network.os, 'name', 'nt'), \
                    patch.object(network.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, result)):
                network.lan_ip.cache_clear()
                with self.assertLogs('utils.network', level='WARNING'):
                    self.assertIsNone(network.lan_ip())

    def test_address_detection_errors_leave_yaml_download_available(self):
        with patch.object(network.os, 'name', 'nt'), \
                patch.object(network.subprocess, 'run', side_effect=subprocess.TimeoutExpired('powershell', 15)), \
                self.assertLogs('utils.network', level='WARNING'):
            self.assertIsNone(network.lan_ip())

    def test_import_url_uses_lan_ip_even_when_page_is_localhost(self):
        with patch.object(network, 'lan_ip', return_value='10.12.64.8'):
            self.assertEqual(network.import_url(self.request(), '/exports/test.yaml'),
                             'http://10.12.64.8:18080/exports/test.yaml')
        with patch.object(network, 'lan_ip', return_value=None):
            self.assertIsNone(network.import_url(self.request(), '/exports/test.yaml'))

    def test_lan_host_allows_only_this_machine_to_perform_operations(self):
        with patch.object(network, 'lan_ip', return_value='10.12.64.8'):
            network.require_local(self.request('10.12.64.8', '10.12.64.8'))
            for host, client in (('10.12.64.8', '10.12.64.9'), ('attacker.invalid', '127.0.0.1')):
                with self.assertRaises(HTTPException) as error:
                    network.require_local(self.request(host, client))
                self.assertEqual(error.exception.status_code, 403)

    def test_download_accepts_private_clients_but_not_public_or_forged_hosts(self):
        with patch.object(network, 'lan_ip', return_value='10.12.64.8'):
            network.require_download(self.request('10.12.64.8', '10.12.64.9'))
            for host, client in (('10.12.64.8', '8.8.8.8'), ('attacker.invalid', '10.12.64.9')):
                with self.assertRaises(HTTPException):
                    network.require_download(self.request(host, client))
