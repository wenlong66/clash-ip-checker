import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen


@unittest.skipUnless(os.name == 'nt', 'Windows batch files')
class WebLauncherTests(unittest.TestCase):
    def launch(self, root, script):
        return self.spawn([os.environ['COMSPEC'], '/d', '/c', f'.\\{script}'], cwd=root)

    def spawn(self, command, cwd=None):
        process = subprocess.Popen(
            command, cwd=cwd,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        self.addCleanup(self.end_process, process)
        return process

    @staticmethod
    def end_process(process):
        if process.poll() is None:
            subprocess.run(['taskkill', '/t', '/f', '/pid', str(process.pid)], capture_output=True)
        process.wait(timeout=5)

    def listening_pid(self, port):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=1) as connection:
                    return int(connection.recv(32))
            except OSError:
                time.sleep(0.1)
        self.fail(f'No listener on port {port}')

    def wait_for_http(self, port):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urlopen(f'http://127.0.0.1:{port}/openapi.json', timeout=1) as response:
                    self.assertEqual(response.status, 200)
                    return
            except OSError:
                time.sleep(0.1)
        self.fail(f'No HTTP listener on port {port}')

    def test_restart_stop_and_refuse_foreign_listener(self):
        temp = tempfile.TemporaryDirectory(prefix='web launchers ')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]

        for name in ('start_web.bat', 'stop_web.bat', 'restart_web.bat'):
            batch = Path(__file__).resolve().parents[1] / name
            (root / name).write_text(batch.read_text().replace('18080', str(port)))
        server = (
            'import os, socket\n'
            'with socket.socket() as listener:\n'
            f'    listener.bind(("127.0.0.1", {port}))\n'
            '    listener.listen()\n'
            '    while True:\n'
            '        connection, _ = listener.accept()\n'
            '        with connection:\n'
            '            connection.sendall(str(os.getpid()).encode())\n'
        )
        (root / 'web.py').write_text(server)

        original = self.launch(root, 'start_web.bat')
        original_pid = self.listening_pid(port)
        restarted = self.launch(root, 'restart_web.bat')
        original.wait(timeout=15)
        self.assertNotEqual(self.listening_pid(port), original_pid)
        self.assertEqual(self.launch(root, 'stop_web.bat').wait(timeout=15), 0)
        restarted.wait(timeout=5)
        self.assertEqual(self.launch(root, 'stop_web.bat').wait(timeout=15), 0)

        legacy_server = (
            'import json, sys\n'
            'from http.server import BaseHTTPRequestHandler, HTTPServer\n'
            'class Handler(BaseHTTPRequestHandler):\n'
            '    def do_GET(self):\n'
            '        title = sys.argv[1] if len(sys.argv) > 1 else "Clash IP Checker"\n'
            '        body = json.dumps({"info": {"title": title}, "paths": {"/api/start": {}}}).encode()\n'
            '        self.send_response(200)\n'
            '        self.send_header("Content-Type", "application/json")\n'
            '        self.end_headers()\n'
            '        self.wfile.write(body)\n'
            f'HTTPServer(("127.0.0.1", {port}), Handler).serve_forever()\n'
        )
        (root / 'web.py').write_text(legacy_server)
        legacy = self.spawn([sys.executable, 'web.py'], cwd=root)
        self.wait_for_http(port)
        stopped = subprocess.run(
            [os.environ['COMSPEC'], '/d', '/c', '.\\stop_web.bat'], cwd=root,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
        )
        self.assertEqual(stopped.returncode, 0, stopped.stderr.decode('ascii', errors='replace'))
        legacy.wait(timeout=5)
        for title in ('Clash IP Checker', 'Another App'):
            with self.subTest(title=title):
                (root / 'web.py').write_text(legacy_server.replace('"Clash IP Checker"', repr(title)))
                legacy = self.spawn([sys.executable, 'web.py'], cwd=root)
                self.wait_for_http(port)
                restarted = self.launch(root, 'restart_web.bat')
                if title == 'Clash IP Checker':
                    legacy.wait(timeout=15)
                    self.wait_for_http(port)
                    self.assertEqual(restarted.poll(), None)
                    self.assertEqual(self.launch(root, 'stop_web.bat').wait(timeout=15), 0)
                    restarted.wait(timeout=5)
                else:
                    self.assertNotEqual(restarted.wait(timeout=15), 0)
                    self.assertEqual(legacy.poll(), None)
                    self.end_process(legacy)

        self.spawn([sys.executable, '-c', server])
        foreign_pid = self.listening_pid(port)
        self.assertNotEqual(self.launch(root, 'restart_web.bat').wait(timeout=15), 0)
        self.assertEqual(self.listening_pid(port), foreign_pid)
