"""Export DNS and routing separately from Shadowrocket node subscriptions."""
from ipaddress import ip_address
import re

from utils.geosite import geosite_domains


def config_value(value, forbidden=',\r\n'):
    if (not isinstance(value, str) or not value.strip() or re.search(r'[\x00-\x1f\x7f]', value)
            or any(char in value for char in forbidden)):
        raise ValueError('DNS 或分流配置包含无法安全转换的参数，请重新提取')
    return value


def shadowrocket_rules_config(config, geosite_path):
    if not isinstance(config, dict) or not isinstance(config.get('dns'), dict):
        raise ValueError('缺少完整 DNS 配置，请重新提取青云梯配置')
    dns = config['dns']
    if (dns.get('enable') is False or dns.get('enhanced-mode', 'fake-ip') != 'fake-ip'
            or dns.get('fake-ip-filter-mode', 'blacklist') != 'blacklist'
            or any(dns.get(key) for key in ('nameserver-policy', 'proxy-server-nameserver-policy',
                                           'fallback-filter', 'respect-rules'))):
        raise ValueError('此 DNS 策略暂不能等价转换为小火箭配置')
    general = []
    for source, target in (('nameserver', 'dns-server'), ('proxy-server-nameserver', 'proxy-dns-server'),
                           ('direct-nameserver', 'direct-dns-server'), ('fallback', 'fallback-dns-server')):
        values = dns.get(source)
        if values:
            if not isinstance(values, list) or any('#' in config_value(value) for value in values):
                raise ValueError('DNS 服务器格式或指定代理出口暂不支持转换')
            general.append(f'{target} = ' + ','.join(values))
    if not dns.get('nameserver'):
        raise ValueError('缺少 DNS 服务器，请重新提取完整配置')
    if not dns.get('fallback'):
        general.append('fallback-dns-server = ' + ','.join(dns['nameserver']))
    ipv6 = bool(config.get('ipv6', False) and dns.get('ipv6', True))
    general += [f'ipv6 = {str(ipv6).lower()}', 'dns-direct-system = false',
                'dns-direct-fallback-proxy = false', 'private-ip-answer = true',
                'udp-policy-not-supported-behaviour = REJECT', 'block-quic = always-allow']
    filters = dns.get('fake-ip-filter', [])
    if not isinstance(filters, list):
        raise ValueError('Fake-IP 过滤规则格式错误')
    real_ip = []
    for value in filters:
        value = config_value(value)
        real_ip.extend([value[2:], '*.' + value[2:]] if value.startswith('+.') else [value])
    if real_ip:
        general.append('always-real-ip = ' + ','.join(real_ip))

    outlets = {item['name'] for key in ('proxies', 'proxy-groups')
               for item in config.get(key, [])
               if isinstance(item, dict) and isinstance(item.get('name'), str)}
    source_rules = config.get('rules')
    if not isinstance(source_rules, list) or not source_rules or config.get('sub-rules'):
        raise ValueError('缺少完整分流规则或包含暂不支持的子规则，请重新提取')
    supported = {'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'DOMAIN-WILDCARD', 'IP-CIDR',
                 'IP-CIDR6', 'GEOIP', 'IP-ASN', 'DST-PORT', 'NETWORK', 'AND', 'OR', 'NOT', 'MATCH', 'GEOSITE'}
    parsed = []
    for rule in source_rules:
        prefix, separator, target = config_value(rule, '\r\n').rpartition(',')
        suffix = ''
        if target == 'no-resolve':
            suffix = ',no-resolve'
            prefix, separator, target = prefix.rpartition(',')
        kind = prefix.split(',', 1)[0]
        types = re.findall(r'(?:^|\()([A-Z][A-Z0-9-]*),', prefix)
        if (not separator or kind not in supported or any(item not in supported for item in types)
                or (kind == 'MATCH' and prefix != 'MATCH') or (kind != 'MATCH' and ',' not in prefix)
                or '(GEOSITE,' in prefix):
            raise ValueError('分流规则包含小火箭暂不支持的类型，不能完整转换')
        if target in outlets:
            target = 'PROXY'
        elif target not in ('DIRECT', 'REJECT', 'REJECT-DROP', 'PROXY'):
            raise ValueError('分流规则引用了不存在的策略，请重新提取完整配置')
        parsed.append((kind, prefix, target, suffix))
    categories = {prefix.split(',', 1)[1] for kind, prefix, _, _ in parsed if kind == 'GEOSITE'}
    domains = geosite_domains(geosite_path, categories)
    rules = []
    regex_count = 0
    for kind, prefix, target, suffix in parsed:
        if kind == 'GEOSITE':
            for domain_type, value in domains[prefix.split(',', 1)[1]]:
                if domain_type == 1:
                    # Shadowrocket has URL-REGEX, not an equivalent DOMAIN-REGEX rule.
                    expression = value.removeprefix('^').removesuffix('$').replace(',', r'\x2c')
                    if expression.startswith(r'(^|\.)'):
                        expression = r'(?:[^/]+\.)?' + expression[len(r'(^|\.)'):]
                    elif not value.startswith('^'):
                        expression = r'[^/]*' + expression
                    value = r'^https?://' + expression + r'(?::[0-9]+)?(?:[/?#]|$)'
                    name = 'URL-REGEX'
                    regex_count += 1
                else:
                    name = {0: 'DOMAIN-KEYWORD', 2: 'DOMAIN-SUFFIX', 3: 'DOMAIN'}[domain_type]
                    config_value(value)
                rules.append(f'{name},{value},{target}{suffix}')
        else:
            prefix = re.sub(r'(^|\()IP-CIDR6,', r'\1IP-CIDR,', prefix)
            prefix = re.sub(r'(^|\()NETWORK,', r'\1PROTOCOL,', prefix)
            rules.append(f'{"FINAL" if kind == "MATCH" else prefix},{target}{suffix}')
    hosts = []
    mappings = config.get('hosts', {})
    if not isinstance(mappings, dict):
        raise ValueError('Host 地址映射格式错误')
    if dns.get('use-hosts') is not False:
        for server, mapping in mappings.items():
            server = config_value(server, ',=[]#;\r\n')
            addresses = mapping if isinstance(mapping, list) else [mapping]
            try:
                addresses = [str(ip_address(address)) for address in addresses]
            except (ValueError, TypeError):
                raise ValueError('Host 映射不是有效 IP，暂不能完整转换') from None
            if not addresses:
                raise ValueError('Host 地址映射为空')
            hosts.append(f'{server} = {addresses[0]}')
    header = ['# 青云梯 DNS 与分流配置（不包含节点或节点凭据）。',
              '# 先用 TXT 导入节点，在首页选中可用节点；再在「配置」中导入并启用本文件，使用「配置」路由。',
              '# PROXY 使用小火箭当前选中的节点；不复制青云梯自动选择或故障转移组。',
              '# 本文件会更换当前启用的 DNS 与分流规则，请先备份原配置；日常连接不依赖原客户端或网页服务。',
              '# 跨内核差异：DNS 引导、Fake-IP 地址段、嗅探及规则优先级由小火箭处理，GeoIP 数据库版本可能不同。']
    if regex_count:
        header.append(f'# 注意：{regex_count} 条 GeoSite 域名正则转换为 HTTP/HTTPS URL 正则；受小火箭 URL 识别能力限制，其他协议不能等价匹配。')
    if any(isinstance(value, list) and len(value) > 1 for value in mappings.values()):
        header.append('# 注意：多个 Host IP 仅写入首个地址；源规则或 IP 变化后需重新生成并导入。')
    sections = [('General', general), ('Rule', rules), ('Host', hosts)]
    return '\n'.join(header) + '\n\n' + '\n\n'.join(f'[{name}]\n' + '\n'.join(lines) for name, lines in sections) + '\n'
