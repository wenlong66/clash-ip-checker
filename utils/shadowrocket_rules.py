"""Export DNS and routing separately from Shadowrocket node subscriptions."""
from ipaddress import ip_address, ip_network
from itertools import product
import re

from utils.geosite import geosite_domains


MAX_REGEX_DOMAINS = 1024
MAX_DOMAIN_LENGTH = 253


def config_value(value, forbidden=',\r\n'):
    if (not isinstance(value, str) or not value.strip() or re.search(r'[\x00-\x1f\x7f]', value)
            or any(char in value for char in forbidden)):
        raise ValueError('DNS 或分流配置包含无法安全转换的参数，请重新提取')
    return value


def finite_domain_rules(expression):
    kind = 'DOMAIN-SUFFIX' if expression.startswith(r'(^|\.)') else 'DOMAIN'
    prefix = len(r'(^|\.)') if kind == 'DOMAIN-SUFFIX' else 1
    if (not expression.endswith('$') or re.search('[A-Z]', expression)
            or kind == 'DOMAIN' and not expression.startswith('^')):
        return None
    remaining = expression[prefix:-1]
    domains = ['']
    while remaining:
        match = re.match(r'\\[.d-]|\[[a-zA-Z0-9-]+\]|\((?:\?:)?[a-zA-Z0-9\\.|-]+\)|[a-zA-Z0-9_-]', remaining)
        if not match:
            return None
        atom = match[0]
        remaining = remaining[match.end():]
        if atom.startswith('['):
            try:
                values = [char for char in 'abcdefghijklmnopqrstuvwxyz0123456789-._'
                          if re.fullmatch(atom, char)]
            except re.error:
                return None
        elif atom.startswith('('):
            values = atom[1:-1].removeprefix('?:').split('|')
            if any(not re.fullmatch(r'(?:[a-zA-Z0-9_-]|\\\.)+', value) for value in values):
                return None
            values = [value.replace(r'\.', '.') for value in values]
        else:
            values = list('0123456789') if atom == r'\d' else [atom.removeprefix('\\')]
        repeat = re.match(r'\{(\d+)(?:,(\d+))?\}|\?', remaining)
        minimum, maximum = 1, 1
        if repeat:
            minimum, maximum = ((0, 1) if repeat[0] == '?' else
                                (int(repeat[1]), int(repeat[2] or repeat[1])))
            remaining = remaining[repeat.end():]
        if (not values or maximum > MAX_DOMAIN_LENGTH or minimum > maximum
                or max(map(len, domains)) + max(map(len, values)) * maximum > MAX_DOMAIN_LENGTH
                or len(domains) * sum(len(values) ** count for count in range(minimum, maximum + 1)) > MAX_REGEX_DOMAINS):
            return None
        variants = [''.join(items) for count in range(minimum, maximum + 1)
                    for items in product(values, repeat=count)]
        domains = [domain + value for domain in domains for value in variants]
    if any(len(domain) > MAX_DOMAIN_LENGTH or not re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*', domain)
           for domain in domains):
        return None
    return [(kind, domain) for domain in dict.fromkeys(domains)]


def url_domain_regex(expression):
    def comma_repeat(match):
        atom, minimum, maximum = match.groups()
        minimum = int(minimum)
        maximum = int(maximum) if maximum else None
        if minimum > MAX_DOMAIN_LENGTH or maximum is not None and not minimum <= maximum <= MAX_DOMAIN_LENGTH:
            raise ValueError('域名正则重复次数超出可转换范围，不能完整导出')
        repeated = f'(?:{atom})'
        return repeated + '{' + str(minimum) + '}' + (repeated + '*' if maximum is None
                                                     else (repeated + '?') * (maximum - minimum))

    expression = re.sub(r'(\\.|\[(?:\\.|[^\\\]])+\]|[^\\\[\](){}*+?])\{(\d+),(\d*)\}',
                        comma_repeat, expression)
    if re.search(r'\{\d+,\d*\}', expression):
        raise ValueError('此域名正则包含不能安全转换的小火箭量词，不能完整导出')
    anchored = expression.startswith('^')
    expression = expression.removeprefix('^').removesuffix('$').replace(',', r'\x2c')
    if expression.startswith(r'(^|\.)'):
        expression = r'(?:[^/]+\.)?' + expression[len(r'(^|\.)'):]
    elif not anchored:
        expression = r'[^/]*' + expression
    return r'^https?://' + expression + r'(?::[0-9]+)?(?:[/?#]|$)'


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
    expanded = []
    for rule in source_rules:
        if not isinstance(rule, str) or not rule.startswith('RULE-SET,'):
            expanded.append(rule)
            continue
        parts = rule.split(',')
        if len(parts) not in (3, 4) or len(parts) == 4 and parts[3] != 'no-resolve':
            raise ValueError('内嵌规则集的选项暂不支持小火箭转换')
        provider = (config.get('rule-providers') or {}).get(parts[1])
        if (not isinstance(provider, dict) or provider.get('type') != 'inline'
                or provider.get('behavior') not in ('classical', 'ipcidr')
                or not isinstance(provider.get('payload'), list)):
            raise ValueError('小火箭仅支持转换已内嵌的规则集，请重新提取配置')
        suffix = ',' + ','.join(parts[2:])
        for entry in provider['payload']:
            entry = config_value(entry, '\r\n')
            if provider['behavior'] == 'ipcidr':
                try:
                    entry = 'IP-CIDR,' + str(ip_network(entry, strict=False))
                except ValueError:
                    raise ValueError('内嵌 IP 规则集含无效网段，不能完整导出') from None
            expanded.append(entry + suffix)
    supported = {'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'DOMAIN-WILDCARD', 'DOMAIN-REGEX', 'IP-CIDR',
                 'IP-CIDR6', 'GEOIP', 'IP-ASN', 'DST-PORT', 'NETWORK', 'AND', 'OR', 'NOT', 'MATCH', 'GEOSITE'}
    parsed = []
    for rule in expanded:
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
        if kind in ('GEOSITE', 'DOMAIN-REGEX'):
            entries = domains[prefix.split(',', 1)[1]] if kind == 'GEOSITE' else [(1, prefix.split(',', 1)[1])]
            for domain_type, value in entries:
                if domain_type == 1:
                    finite = finite_domain_rules(value)
                    if finite is not None:
                        rules.extend(f'{name},{domain},{target}{suffix}' for name, domain in finite)
                        continue
                    # shortcut: non-finite regexes remain HTTP/HTTPS-only until a native domain-regex rule is supported.
                    value = url_domain_regex(value)
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
        header.append(f'# 注意：仍有 {regex_count} 条域名正则仅转换为 HTTP/HTTPS URL 正则；受小火箭 URL 识别能力限制，其他协议不能等价匹配。')
    if any(isinstance(value, list) and len(value) > 1 for value in mappings.values()):
        header.append('# 注意：多个 Host IP 仅写入首个地址；源规则或 IP 变化后需重新生成并导入。')
    sections = [('General', general), ('Rule', rules), ('Host', hosts)]
    return '\n'.join(header) + '\n\n' + '\n\n'.join(f'[{name}]\n' + '\n'.join(lines) for name, lines in sections) + '\n'
