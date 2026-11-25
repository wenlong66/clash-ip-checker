"""Keep portable connection settings without copying a client's control endpoints."""
import copy
from ipaddress import ip_address
from urllib.parse import unquote


RUNTIME_FIELDS = (
    "mixed-port", "port", "socks-port", "redir-port", "tproxy-port",
    "external-controller", "external-controller-tls", "external-controller-unix",
    "external-controller-pipe", "external-ui", "external-ui-url", "secret",
    "interface-name", "auto-detect-interface", "authentication",
)


def portable_config(config, server_hosts=None):
    result = copy.deepcopy(config)
    for field in RUNTIME_FIELDS:
        result.pop(field, None)
    if isinstance(result.get("tun"), dict):
        for field in ("device", "file-descriptor", "interface-name"):
            result["tun"].pop(field, None)
    if isinstance(result.get("dns"), dict):
        result["dns"].pop("listen", None)
    if server_hosts:
        result["hosts"] = {**(result.get("hosts") or {}), **copy.deepcopy(server_hosts)}
        result.setdefault("dns", {}).update({"enable": True, "use-hosts": True})
    return result


def qingyunti_backup_dns(config, backups, primary_server):
    dns = config['dns']
    policies = dns.get('proxy-server-nameserver-policy', {})
    if not isinstance(policies, dict):
        raise ValueError('主用订阅的节点 DNS 策略格式错误')
    overrides = {}
    for server, source in backups:
        try:
            ip_address(server)
            continue
        except ValueError:
            pass
        server = server.rstrip('.').lower()
        hostnames = {name.rstrip('.').lower() for name in config.get('hosts', {})}
        if dns.get('use-hosts') is not False and server in hostnames:
            continue
        source_dns = source.get('dns', {})
        if not isinstance(source_dns, dict):
            raise ValueError('备用订阅的 DNS 格式错误')
        dedicated = source_dns.get('proxy-server-nameserver')
        if (source_dns.get('proxy-server-nameserver-policy')
                or not dedicated and source_dns.get('nameserver-policy')):
            raise ValueError('备用订阅包含独立 DNS 分流，暂不能完整继承，请使用独立节点解析配置')
        nameservers = dedicated or source_dns.get('nameserver') or ['system']
        if source_dns.get('enable') is False:
            nameservers = ['system']
        if (not isinstance(nameservers, list)
                or any(not isinstance(value, str) or not value.strip() for value in nameservers)):
            raise ValueError('备用订阅的节点 DNS 服务器格式错误')
        outlets = {item['name'] for key in ('proxies', 'proxy-groups')
                   for item in source.get(key, []) if isinstance(item, dict) and 'name' in item}
        if any(unquote(value.partition('#')[2].split('&')[0]) in outlets for value in nameservers):
            raise ValueError('备用节点 DNS 依赖原订阅的代理出口，不能独立解析')
        if server == primary_server.rstrip('.').lower():
            primary_dns = policies.get(server, dns.get('proxy-server-nameserver')
                                       or dns.get('nameserver') or ['system'])
            if nameservers != primary_dns:
                raise ValueError('主备共用服务器域名但 DNS 不同，无法独立解析，请换一个备用节点')
            continue
        if server in overrides and overrides[server] != nameservers:
            raise ValueError('备用节点共用服务器域名但 DNS 不同，请换一个备用节点')
        overrides = {**overrides, server: copy.deepcopy(nameservers)}
    return {**copy.deepcopy(dns), 'proxy-server-nameserver-policy': {
        **copy.deepcopy(policies), **overrides}} if overrides else copy.deepcopy(dns)


def qingyunti_failover_policy(source, hosts):
    if not isinstance(source.get("dns"), dict) or not source.get("rules"):
        raise ValueError("青云梯策略需要完整的 DNS 和分流规则，请将完整青云梯导出配置作为主用订阅")
    if source.get("sub-rules"):
        raise ValueError("青云梯策略暂不支持子规则，请使用原始青云梯导出配置")
    config = portable_config(source)
    outlets = {item["name"] for key in ("proxies", "proxy-groups")
               for item in source.get(key, []) if isinstance(item, dict) and "name" in item}
    builtins = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}
    rules = []
    for rule in source["rules"]:
        if not isinstance(rule, str):
            raise ValueError("主用订阅的分流规则格式错误")
        prefix, separator, target = rule.rpartition(",")
        suffix = ""
        while target in ("no-resolve", "src"):
            suffix = "," + target + suffix
            prefix, separator, target = prefix.rpartition(",")
        if not separator or prefix.startswith("SUB-RULE,"):
            raise ValueError("青云梯策略包含暂不支持的分流规则")
        if target in outlets:
            target = "主备切换"
        elif target not in builtins:
            raise ValueError("主用订阅的规则引用了不存在的策略，请重新提取完整配置")
        rules.append(f"{prefix},{target}{suffix}")
    config["rules"] = rules
    config["mode"] = "rule"
    config.pop("proxy-providers", None)

    def dns_outlets(value):
        if isinstance(value, dict):
            return {key: dns_outlets(item) for key, item in value.items()}
        if isinstance(value, list):
            return [dns_outlets(item) for item in value]
        if isinstance(value, str):
            address, separator, fragment = value.partition("#")
            policy, *options = fragment.split("&")
            if separator and unquote(policy) in outlets:
                return address + "#" + "&".join(["主备切换", *options])
        return value

    config["dns"] = dns_outlets(config["dns"])
    providers = config.get("rule-providers", {})
    if not isinstance(providers, dict):
        raise ValueError("主用订阅的规则集格式错误")
    for provider in providers.values():
        if not isinstance(provider, dict) or provider.get("type") not in ("http", "inline"):
            raise ValueError("青云梯策略不支持依赖本地文件的规则集，请使用完整原始导出配置")
        if provider.get("proxy") in outlets:
            provider["proxy"] = "主备切换"
    merged_hosts = config.get("hosts", {})
    if not isinstance(merged_hosts, dict):
        raise ValueError("主用订阅的服务器地址映射格式错误")
    if any(server in merged_hosts and merged_hosts[server] != mapping for server, mapping in hosts.items()):
        raise ValueError("备用节点与主用策略的服务器地址映射冲突，请换一个节点")
    if hosts:
        config["hosts"] = {**merged_hosts, **hosts}
        config["dns"].update({"enable": True, "use-hosts": True})
    return config
