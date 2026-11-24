"""Convert the locally extracted VLESS/TLS nodes to Shadowrocket share links."""
from ipaddress import ip_address
import re
from urllib.parse import quote, urlencode
from uuid import UUID


def shadowrocket_subscription(config):
    nodes = config.get('proxies') if isinstance(config, dict) else None
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 256:
        raise ValueError('导出须包含 1–256 个节点，请重新提取')
    hosts = config.get('hosts', {})
    if not isinstance(hosts, dict):
        raise ValueError('节点地址映射格式错误，请重新提取')
    return '\n'.join(shadowrocket_uri(node, hosts) for node in nodes) + '\n'


def shadowrocket_uri(node, hosts):
    if (not isinstance(node, dict) or node.get('type') != 'vless' or node.get('tls') is not True
            or node.get('network', 'tcp') != 'tcp' or node.get('reality-opts') or node.get('dialer-proxy')):
        raise ValueError('Shadowrocket 导出仅支持独立的 VLESS / TCP / TLS 节点')
    name, server = node.get('name'), node.get('server')
    port, sni = node.get('port'), node.get('servername') or server
    flow = node.get('flow') or ''
    if (not isinstance(name, str) or not name.strip() or len(name) > 128 or re.search(r'[\x00-\x1f\x7f]', name)
            or not isinstance(server, str) or not isinstance(sni, str)
            or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', sni)
            or type(port) is not int or not 0 < port < 65536 or flow not in ('', 'xtls-rprx-vision')
            or type(node.get('skip-cert-verify', False)) is not bool):
        raise ValueError('节点名称、TLS/SNI、端口或 flow 格式错误，请重新提取')
    try:
        credential = str(UUID(node['uuid']))
        mapped = hosts.get(server, server)
        address = str(ip_address(mapped[0] if isinstance(mapped, list) and mapped else mapped))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError('节点缺少有效 UUID 或实际服务器 IP，请保持梯子连接后重新提取') from None
    query = {'encryption': 'none', 'security': 'tls', 'type': 'tcp', 'sni': sni}
    if flow:
        query = {**query, 'flow': flow}
    if node.get('skip-cert-verify'):
        query = {**query, 'allowInsecure': '1'}
    if 'udp' in node:
        if type(node['udp']) is not bool:
            raise ValueError('节点 UDP 参数格式错误，请重新提取')
        query['udp'] = '1' if node['udp'] else '0'
    address = f'[{address}]' if ':' in address else address
    return f'vless://{credential}@{address}:{port}?{urlencode(query)}#{quote(name, safe="")}'
