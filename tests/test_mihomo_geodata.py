import copy
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
from queue import Queue
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import unittest
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError, URLError

import yaml

from test_geosite import field
from utils.geoip import geoip_networks
from utils.qingyunti_geodata import qingyunti_geodata, runtime_data_directory


CORE = Path(r'D:\Program Files\Clash Verge\verge-mihomo.exe')


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class NodeDnsFixture(socketserver.BaseRequestHandler):
    def handle(self):
        data, connection = self.request
        offset = 12
        labels = []
        while data[offset]:
            size = data[offset]
            labels.append(data[offset + 1:offset + size + 1].decode('ascii'))
            offset += size + 1
        query_type = int.from_bytes(data[offset + 1:offset + 3], 'big')
        self.server.received.put((self.server.label, '.'.join(labels)))
        answer_count = int(self.server.answer is not None and query_type == 1)
        answer = (b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 30, 4)
                  + socket.inet_aton(self.server.answer)) if answer_count else b''
        flags = 0x8180 if self.server.answer is not None else 0x8183
        response = (data[:2] + struct.pack('!HHHHH', flags, 1, answer_count, 0, 0)
                    + data[12:offset + 5] + answer)
        connection.sendto(response, self.client_address)


class NodeDnsHttpFixture(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.server.received.put(('origin', 204))
        self.send_response(204)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_CONNECT(self):
        origin = self.server.origin
        if self.path != f'127.0.0.1:{origin.server_address[1]}':
            self.send_error(403)
            return
        self.connection.settimeout(3)
        self.send_response(200)
        self.end_headers()
        self.wfile.flush()
        connection = HTTPConnection('127.0.0.1', origin.server_address[1], timeout=2)
        try:
            method, path, _ = self.rfile.readline().decode('ascii').split()
            while self.rfile.readline().strip():
                pass
            connection.request(method, path)
            response = connection.getresponse()
            response.read()
            self.server.received.put(('proxy', response.status))
            self.wfile.write(f'HTTP/1.1 {response.status} No Content\r\n'
                             'Content-Length: 0\r\nConnection: close\r\n\r\n'.encode('ascii'))
            self.wfile.flush()
        except OSError:
            return
        finally:
            connection.close()
            self.close_connection = True

    def log_message(self, *_):
        pass


@unittest.skipUnless(CORE.is_file(), 'Local Mihomo executable is not installed')
class MihomoGeodataTests(unittest.TestCase):
    def routed_outbounds(self, source, targets, data_directory):
        received = Queue()

        class Proxy(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(3)
                try:
                    line = self.rfile.readline().decode('ascii')
                    if not line.startswith('CONNECT '):
                        return
                    while self.rfile.readline().strip():
                        pass
                    self.wfile.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
                    self.wfile.flush()
                    if self.rfile.read(1):
                        received.put((self.server.outbound, line.split()[1]))
                except OSError:
                    return

        servers = []
        config = copy.deepcopy(source)
        config['proxies'] = []
        for name in ('YES', 'NO'):
            server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Proxy)
            server.outbound = name
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()
            servers.append(server)
            config['proxies'].append({'name': name, 'type': 'http', 'server': '127.0.0.1',
                                      'port': server.server_address[1]})
        port, controller = unused_port(), unused_port()
        config.update({'mode': 'rule', 'mixed-port': port, 'external-controller': f'127.0.0.1:{controller}',
                       'secret': 'fixture-secret', 'allow-lan': False, 'log-level': 'info',
                       'geodata-mode': False, 'geo-auto-update': False,
                       'geox-url': {'mmdb': 'http://127.0.0.1:9/unavailable',
                                    'geosite': 'http://127.0.0.1:9/unavailable'}})
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix='qyt-geodata-test-') as directory:
                directory = Path(directory)
                for name in ('GeoSite.dat', 'geoip.metadb', 'Country.mmdb'):
                    path = data_directory / name
                    if path.is_file():
                        shutil.copyfile(path, directory / name)
                path = directory / 'test.yaml'
                path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
                process = subprocess.Popen([str(CORE), '-d', str(directory), '-f', str(path)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
                ready = threading.Event()
                logs = []

                def collect_logs():
                    for line in process.stdout:
                        logs.append(line)
                        if 'Mixed(http+socks) proxy listening at' in line:
                            ready.set()

                reader = threading.Thread(target=collect_logs, daemon=True)
                reader.start()
                try:
                    self.assertTrue(ready.wait(5), ''.join(logs))
                    opener = build_opener(ProxyHandler({}))
                    for _ in range(100):
                        request = Request(f'http://127.0.0.1:{controller}/providers/rules',
                                          headers={'Authorization': 'Bearer fixture-secret'})
                        try:
                            with opener.open(request, timeout=1) as response:
                                providers = json.load(response).get('providers', {})
                            if all(providers.get(name, {}).get('ruleCount', 0) > 0
                                   for name in config.get('rule-providers', {})):
                                break
                        except (URLError, HTTPException):
                            continue
                    else:
                        self.fail('Inline rule providers did not initialize')
                    outbounds = []
                    for target in targets:
                        with socket.create_connection(('127.0.0.1', port), timeout=3) as sock:
                            sock.sendall(f'CONNECT {target}:443 HTTP/1.1\r\nHost: {target}:443\r\n\r\n'.encode())
                            sock.recv(4096)
                            try:
                                sock.sendall(b'fixture payload')
                            except OSError:
                                pass
                            outbound, actual_target = received.get(timeout=3)
                            self.assertEqual(actual_target, f'{target}:443')
                            outbounds.append(outbound)
                    return outbounds
                finally:
                    process.terminate()
                    process.wait(timeout=5)
                    reader.join(timeout=2)
                    process.stdout.close()
                    process = None
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=5)
            for server in servers:
                server.shutdown()
                server.server_close()

    def node_dns_case(self, dns, proxy):
        controller, mixed, listener = unused_port(), unused_port(), unused_port()
        config = {
            'mode': 'rule', 'mixed-port': mixed, 'allow-lan': False,
            'bind-address': '127.0.0.1', 'external-controller': f'127.0.0.1:{controller}',
            'secret': 'node-dns-fixture', 'log-level': 'info', 'ipv6': False,
            'tun': {'enable': False}, 'geo-auto-update': False,
            'geox-url': {'mmdb': 'http://127.0.0.1:9/unavailable',
                        'geosite': 'http://127.0.0.1:9/unavailable'},
            'proxies': [{'name': 'BACKUP', 'type': 'http', 'server': 'backup.example.invalid',
                         'port': proxy.server_address[1]}],
            'rules': ['MATCH,BACKUP'],
            'dns': {**dns, 'listen': f'127.0.0.1:{listener}'},
        }
        with tempfile.TemporaryDirectory(prefix='qyt-node-dns-test-') as directory:
            path = Path(directory) / 'test.yaml'
            path.write_text(yaml.safe_dump(config), encoding='utf-8')
            process = subprocess.Popen([str(CORE), '-d', directory, '-f', str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            ready = threading.Event()
            logs = []

            def collect_logs():
                for line in process.stdout:
                    logs.append(line)
                    if 'Mixed(http+socks) proxy listening at' in line:
                        ready.set()

            reader = threading.Thread(target=collect_logs, daemon=True)
            reader.start()
            try:
                self.assertTrue(ready.wait(5), ''.join(logs))
                opener = build_opener(ProxyHandler({}))
                endpoint = f'http://127.0.0.1:{controller}'
                headers = {'Authorization': 'Bearer node-dns-fixture'}
                target = f'http://127.0.0.1:{proxy.origin.server_address[1]}/alive'
                try:
                    request = Request(endpoint + '/proxies/BACKUP/delay?timeout=1500&url=' + target,
                                      headers=headers)
                    with opener.open(request, timeout=5) as response:
                        status = response.status
                        json.load(response)
                except HTTPError as error:
                    status = error.code
                    error.close()
                answers = {}
                for domain in ('website-default.example.invalid', 'website-policy.example.invalid'):
                    request = Request(endpoint + f'/dns/query?name={domain}&type=A', headers=headers)
                    with opener.open(request, timeout=3) as response:
                        answers[domain] = [item['data'] for item in json.load(response).get('Answer', [])
                                           if item.get('type') == 1]
                return status, answers
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                reader.join(timeout=2)
                process.stdout.close()

    def test_backup_dns_exception_preserves_website_dns(self):
        from utils.clash_config import qingyunti_backup_dns

        dns_received, http_received = Queue(), Queue()
        servers = []

        def start(server):
            server.daemon_threads = True
            servers.append(server)
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02},
                             daemon=True).start()
            return server

        def resolver(label, answer):
            server = socketserver.ThreadingUDPServer(('127.0.0.1', 0), NodeDnsFixture)
            server.label, server.answer, server.received = label, answer, dns_received
            start(server)
            return f'udp://127.0.0.1:{server.server_address[1]}'

        try:
            default_node = resolver('default-node', None)
            backup_node = resolver('backup-node', '127.0.0.1')
            website_default = resolver('website-default', '192.0.2.31')
            website_policy = resolver('website-policy', '192.0.2.32')
            origin = ThreadingHTTPServer(('127.0.0.1', 0), NodeDnsHttpFixture)
            origin.received = http_received
            start(origin)
            proxy = ThreadingHTTPServer(('127.0.0.1', 0), NodeDnsHttpFixture)
            proxy.origin, proxy.received = origin, http_received
            start(proxy)
            source = {
                'hosts': {'primary.example.invalid': '192.0.2.1'},
                'dns': {'enable': True, 'enhanced-mode': 'redir-host', 'ipv6': False,
                        'default-nameserver': [website_default], 'nameserver': [website_default],
                        'nameserver-policy': {'website-policy.example.invalid': [website_policy]},
                        'proxy-server-nameserver': [default_node]},
            }
            backups = [('backup.example.invalid', {'dns': {'proxy-server-nameserver': [backup_node]}})]
            original = copy.deepcopy(source)
            fixed = qingyunti_backup_dns(source, backups, 'primary.example.invalid')
            self.assertEqual(source, original)
            for key, value in source['dns'].items():
                self.assertEqual(fixed[key], value)
            for enabled, dns in ((False, source['dns']), (True, fixed)):
                with self.subTest(backup_dns_exception=enabled):
                    status, answers = self.node_dns_case(dns, proxy)
                    self.assertEqual(status, 200 if enabled else 503)
                    self.assertEqual(answers, {'website-default.example.invalid': ['192.0.2.31'],
                                               'website-policy.example.invalid': ['192.0.2.32']})
                    observed = [dns_received.get_nowait() for _ in range(dns_received.qsize())]
                    node_queries = [label for label, name in observed if name == 'backup.example.invalid']
                    self.assertEqual(set(node_queries), {'backup-node' if enabled else 'default-node'})
                    self.assertIn(('website-default', 'website-default.example.invalid'), observed)
                    self.assertIn(('website-policy', 'website-policy.example.invalid'), observed)
                    visits = [http_received.get_nowait() for _ in range(http_received.qsize())]
                    self.assertCountEqual(visits, [('origin', 204), ('proxy', 204)] if enabled else [])
        finally:
            for server in reversed(servers):
                server.shutdown()
                server.server_close()

    def test_geosite_regex_comma_matches_the_original_database(self):
        regex = r'^a{1,3}\.example\.invalid$'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cn = field(1, field(1, 'CN') + field(2, field(1, 2) + field(2, 'cn.invalid')))
            database = cn + field(1, field(1, 'TEST') + field(2, field(1, 1) + field(2, regex)))
            (directory / 'GeoSite.dat').write_bytes(database)
            source = {'rules': ['GEOSITE,test,YES', 'MATCH,NO']}
            converted = qingyunti_geodata(source, directory)
            targets = [f'{label}.example.invalid' for label in ('a', 'aa', 'aaa', 'aaaa')]
            original = self.routed_outbounds(source, targets, directory)
            self.assertEqual(original, ['YES', 'YES', 'YES', 'NO'])
            self.assertEqual(self.routed_outbounds(converted, targets, directory), original)

    def test_geoip_matches_original_database_without_external_connections(self):
        try:
            data_directory = runtime_data_directory()
        except ValueError:
            self.skipTest('Verified Qingyunti runtime database is not available')
        networks = geoip_networks(data_directory / 'geoip.metadb', {'CN'})['CN']
        selected = [ipaddress.ip_network(value) for value in networks]
        ipv4 = [str(net.network_address + 1) for net in selected if net.version == 4 and net.num_addresses > 1][:8]
        ipv6 = [f'[{net.network_address + 1}]' for net in selected if net.version == 6 and net.num_addresses > 1][:8]
        targets = [*ipv4, *ipv6, '8.8.8.8', '1.1.1.1', '127.0.0.1', '[2001:db8::1]']
        source = {'rules': ['GEOIP,CN,YES,no-resolve', 'MATCH,NO']}
        converted = qingyunti_geodata(source, data_directory)
        original = self.routed_outbounds(source, targets, data_directory)
        self.assertIn('YES', original)
        self.assertIn('NO', original)
        self.assertEqual(self.routed_outbounds(converted, targets, data_directory), original)


if __name__ == '__main__':
    unittest.main()
