"""Advertise a physical LAN address without exposing local management operations."""
from functools import lru_cache
from ipaddress import ip_address
import logging
import os
import socket
import subprocess
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

LOOPBACK_HOSTS = frozenset({'127.0.0.1', '::1', 'localhost'})
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def lan_ip():
    # shortcut: choose the first physical adapter with a gateway; revisit if multiple LANs need separate import addresses.
    try:
        if os.name == 'nt':
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                 'Get-NetIPConfiguration | Where-Object { $_.NetAdapter.HardwareInterface -and '
                 '$_.IPv4DefaultGateway -and $_.IPv4Address } | '
                 'Sort-Object { $_.NetIPv4Interface.InterfaceMetric } | Select-Object -First 1 | '
                 'ForEach-Object { $_.IPv4Address.IPAddress }'],
                capture_output=True, text=True, check=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            address = ip_address(result.stdout.strip())
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.connect(('192.0.2.1', 80))
                address = ip_address(connection.getsockname()[0])
        if address.version == 4 and address.is_private and not address.is_loopback and not address.is_link_local:
            return str(address)
        logger.warning('No usable private LAN IPv4 address found')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        logger.warning('Unable to detect LAN IPv4 address: %s', error)
    return None


def local_hosts():
    address = lan_ip()
    return LOOPBACK_HOSTS | {address} if address else LOOPBACK_HOSTS


def require_local(request: Request):
    hosts = local_hosts()
    if not request.client or request.client.host not in hosts or request.url.hostname not in hosts:
        raise HTTPException(status_code=403, detail='仅允许本机通过 localhost、127.0.0.1 或本机局域网 IP 操作')
    origin = request.headers.get('origin')
    if origin and urlsplit(origin).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail='仅允许当前网页读取本机订阅')


def require_download(request: Request):
    if not request.client or request.url.hostname not in local_hosts():
        raise HTTPException(status_code=403, detail='请通过本机或局域网地址下载订阅')
    try:
        client = ip_address(request.client.host)
    except ValueError:
        raise HTTPException(status_code=403, detail='无效的下载客户端地址') from None
    if not client.is_private or client.is_link_local or client.is_unspecified:
        raise HTTPException(status_code=403, detail='订阅仅允许本机和局域网下载')
    origin = request.headers.get('origin')
    if origin and urlsplit(origin).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail='仅允许同源下载订阅')


def import_url(request: Request, path: str):
    address = lan_ip()
    if not address:
        return None
    port = f':{request.url.port}' if request.url.port else ''
    return f'{request.url.scheme}://{address}{port}{path}'
