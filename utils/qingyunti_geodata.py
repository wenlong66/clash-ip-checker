"""Freeze Qingyunti geodata inside its own configuration, not Clash's shared cache."""
import base64
import copy
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import subprocess

from utils.geoip import geoip_networks
from utils.geosite import geosite_domains


APEX_CORE = Path(r'D:\Users\long\AppData\Local\Programs\青云梯-极速版\ApexCore.exe')
DOMAIN_TYPES = {0: 'DOMAIN-KEYWORD', 1: 'DOMAIN-REGEX', 2: 'DOMAIN-SUFFIX', 3: 'DOMAIN'}


def runtime_data_directory(pid=None):
    try:
        process_filter = f'ProcessId = {int(pid)}' if pid is not None else "Name = 'ApexCore.exe'"
        script = (f'$p = Get-CimInstance Win32_Process -Filter "{process_filter}"; '
                  '[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(('
                  '$p | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress)))')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=15, check=True)
        processes = json.loads(base64.b64decode(result.stdout.strip(), validate=True).decode('utf-8'))
        processes = processes if isinstance(processes, list) else [processes]
        if len(processes) != 1:
            raise ValueError('Expected one core')
        process = processes[0]
        if (Path(process['ExecutablePath']) != APEX_CORE
                or not isinstance(process.get('CommandLine'), str)
                or pid is not None and process['ProcessId'] != int(pid)):
            raise ValueError('Core identity mismatch')
        arguments = shlex.split(process['CommandLine'], posix=False)
        directory = next((arguments[index + 1].strip('"') for index, value in enumerate(arguments[:-1])
                          if value == '-d'), None)
        directory = directory or next((value[3:].strip('"') for value in arguments if value.startswith('-d=')), None)
        if directory is None or not Path(directory).is_absolute() or not Path(directory).is_dir():
            raise ValueError('Missing absolute runtime directory')
        return Path(directory)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        raise ValueError('无法确认青云梯运行内核的数据目录，请保持已核实的客户端运行后重新提取') from None


def uses_geodata(value):
    if isinstance(value, dict):
        return any(uses_geodata(key) or uses_geodata(item) for key, item in value.items())
    if isinstance(value, list):
        return any(uses_geodata(item) for item in value)
    return isinstance(value, str) and re.search(r'(?:^|\()(?:SRC-)?(?:GEOSITE|GEOIP|IP-ASN)[:,]', value, re.IGNORECASE) is not None


def qingyunti_geodata(source, directory=None, *, pid=None):
    rules = source.get('rules', [])
    if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
        raise ValueError('青云梯分流规则格式错误，请重新提取完整配置')
    dns = source.get('dns') or {}
    if not isinstance(dns, dict):
        raise ValueError('青云梯 DNS 配置格式错误')
    fallback_filter = dns.get('fallback-filter') or {}
    if not isinstance(fallback_filter, dict):
        raise ValueError('青云梯 DNS 过滤配置格式错误')
    if (uses_geodata(dns) or fallback_filter.get('geosite')
            or dns.get('fallback') and fallback_filter.get('geoip', True)):
        raise ValueError('此 DNS 策略依赖共享 Geo 数据库，暂不能完整隔离，请使用原始客户端配置')
    providers = source.get('rule-providers', {})
    if not isinstance(providers, dict):
        raise ValueError('青云梯规则集格式错误')
    for provider in providers.values():
        if isinstance(provider, dict) and provider.get('type') == 'inline' and uses_geodata(provider.get('payload')):
            raise ValueError('内嵌规则集仍依赖 Geo 数据库，暂不能完整固化，请使用原始客户端配置')
    if source.get('sub-rules') or any(re.search(r'\((?:SRC-)?GEO(?:SITE|IP),|^SRC-GEOIP,', rule) for rule in rules):
        raise ValueError('暂不支持固化子规则或嵌套的 Geo 分类，请使用原始客户端配置')
    categories = {kind: {rule.split(',')[1] for rule in rules if rule.startswith(kind + ',')}
                  for kind in ('GEOSITE', 'GEOIP')}
    if not any(categories.values()):
        return copy.deepcopy(source)
    if categories['GEOIP'] and source.get('geodata-mode'):
        raise ValueError('此配置使用 GeoIP.dat，暂不支持按 MMDB 数据库固化，请使用原始客户端配置')
    directory = Path(directory) if directory is not None else runtime_data_directory(pid)
    sites = geosite_domains(directory / 'GeoSite.dat', categories['GEOSITE'])
    ips = geoip_networks(directory / 'geoip.metadb', categories['GEOIP'])
    additions = {}
    names = {}
    for kind, entries in (('GEOSITE', sites), ('GEOIP', ips)):
        for category, values in entries.items():
            payload = [f'{DOMAIN_TYPES[typ]},{text}' for typ, text in values] if kind == 'GEOSITE' else values
            digest = sha256('\n'.join(payload).encode('utf-8')).hexdigest()[:16]
            name = f'qingyunti-{kind.lower()}-{digest}'
            provider = {'type': 'inline', 'behavior': 'classical' if kind == 'GEOSITE' else 'ipcidr',
                        'payload': payload}
            if name in providers and providers[name] != provider:
                raise ValueError('青云梯内嵌规则集名称冲突，请重新提取配置')
            additions = {**additions, name: provider}
            names[(kind, category)] = name
    converted = []
    for rule in rules:
        kind = rule.split(',', 1)[0]
        if kind in categories:
            parts = rule.split(',', 2)
            if len(parts) != 3 or not parts[2]:
                raise ValueError('青云梯 Geo 分类规则不完整')
            rule = f'RULE-SET,{names[(kind, parts[1])]},{parts[2]}'
        converted.append(rule)
    return {**copy.deepcopy(source), 'rules': converted,
            'rule-providers': {**copy.deepcopy(providers), **additions}}
