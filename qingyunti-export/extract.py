"""Export a loaded ApexCore Clash config without writing a memory dump."""
import argparse
import ctypes as c
import ctypes.wintypes as w
from ipaddress import ip_address
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.clash_config import portable_config
from utils.qingyunti_geodata import APEX_CORE, qingyunti_geodata


def parse_config(raw):
    try:
        text = raw.decode("utf-8")
        config = json.loads(text) if text.lstrip().startswith("{") else yaml.safe_load(text)
    except (UnicodeError, ValueError, yaml.YAMLError):
        return None
    if not isinstance(config, dict):
        return None
    proxies = config.get("proxies")
    if not isinstance(proxies, list) or not proxies:
        return None
    if not all(isinstance(p, dict) and p.get("name") and p.get("server") and p.get("type") for p in proxies):
        return None
    if len({p["name"] for p in proxies}) != len(proxies):
        return None
    return config


def config_candidates(raw):
    result = []
    checked = set()
    decoder = json.JSONDecoder()
    for match in re.finditer(rb'(?m)^proxies\s*:|"proxies"\s*:\s*\[', raw):
        lower = max(0, match.start() - 2_000_000)
        upper = min(len(raw), match.end() + 2_000_000)
        start = raw.rfind(b'\0', lower, match.start()) + 1
        end = raw.find(b'\0', match.end(), upper)
        config = parse_config(raw[start:end]) if end >= 0 else None
        if not config:
            starts = [lower + item.start() for item in re.finditer(rb'\{', raw[lower:match.start()])][-512:]
            for offset in reversed(starts):
                if offset in checked:
                    continue
                checked.add(offset)
                text = raw[offset:upper].decode('utf-8', errors='replace')
                try:
                    _, length = decoder.raw_decode(text)
                except (ValueError, RecursionError):
                    continue
                config = parse_config(text[:length].encode('utf-8'))
                if config:
                    break
        if config and config not in result:
            result.append(config)
    return result


def active_server_hosts(pid, proxies):
    domains = {p["server"] for p in proxies}
    for server in tuple(domains):
        try:
            ip_address(server)
        except ValueError:
            continue
        domains = domains - {server}
    if not domains:
        return {}
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         f"ConvertTo-Json -Compress -InputObject @(Get-NetTCPConnection -OwningProcess {pid} "
         "-State Established -ErrorAction Stop | Select-Object RemoteAddress,RemotePort)"],
        capture_output=True, text=True, timeout=15, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        connections = json.loads(result.stdout)
        if not isinstance(connections, list):
            raise ValueError("Expected a connection list")
        ports = {int(p["port"]) for p in proxies}
        if not all(0 < port < 65536 for port in ports):
            raise ValueError("Invalid node port")
        port_servers = {port: {p["server"] for p in proxies if int(p["port"]) == port} for port in ports}
        endpoints = [(int(conn["RemotePort"]), str(ip_address(conn["RemoteAddress"]))) for conn in connections]
    except (ValueError, TypeError, KeyError) as error:
        raise RuntimeError("无法读取 Apex 活动节点地址，请保持客户端连接后重试") from error
    if any(len(port_servers[port]) != 1 for port, _ in endpoints if port in port_servers):
        raise RuntimeError("无法唯一匹配 Apex 活动节点地址，节点端口存在冲突")
    # shortcut: match live sockets by unique node ports; use authenticated metadata if Apex shares ports across servers.
    hosts = {server: sorted({address for port, address in endpoints
                             if port_servers.get(port) == {server}}) for server in domains}
    if not all(hosts.values()):
        raise RuntimeError("未找到节点服务器的活动连接，请在 Apex 连接节点并打开网页后重新提取")
    return hosts


def extract(pid):
    class MemoryInfo(c.Structure):
        _fields_ = [("base", c.c_void_p), ("allocation", c.c_void_p),
                    ("allocation_protect", w.DWORD), ("size", c.c_size_t),
                    ("state", w.DWORD), ("protect", w.DWORD), ("kind", w.DWORD)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    kernel.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MemoryInfo), c.c_size_t]
    kernel.VirtualQueryEx.restype = c.c_size_t
    kernel.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x410, False, pid)  # Query information + read memory only.
    if not handle:
        raise c.WinError(c.get_last_error())
    found = None
    try:
        path = c.create_unicode_buffer(32768)
        length = w.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, c.byref(length)):
            raise c.WinError(c.get_last_error())
        if Path(path.value) != APEX_CORE:
            raise RuntimeError("PID does not belong to the expected ApexCore.exe")
        address = 0
        info = MemoryInfo()
        while kernel.VirtualQueryEx(handle, address, c.byref(info), c.sizeof(info)):
            address = (info.base or 0) + info.size
            if info.state != 0x1000 or info.kind != 0x20000 or info.protect not in (2, 4, 8, 0x20, 0x40, 0x80):
                continue
            if info.size > 256 * 1024 * 1024:
                continue
            buf = c.create_string_buffer(info.size)
            count = c.c_size_t()
            if not kernel.ReadProcessMemory(handle, info.base, buf, info.size, c.byref(count)):
                continue
            raw = buf.raw[:count.value]
            for config in config_candidates(raw):
                if found is None or len(config["proxies"]) > len(found["proxies"]):
                    found = config
    finally:
        kernel.CloseHandle(handle)
    if found is None:
        raise RuntimeError("No complete config found; keep Apex connected and retry, or recheck client version")
    return portable_config(found, active_server_hosts(pid, found["proxies"]))


def find_pid():
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "Get-Process -Name ApexCore -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
        capture_output=True, text=True, timeout=15, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    pids = result.stdout.split()
    if not pids:
        raise RuntimeError("未找到 ApexCore，请先启动青云梯极速版并加载节点")
    if len(pids) != 1:
        raise RuntimeError("存在多个 ApexCore 实例，请仅保留要导出的青云梯实例后重试")
    return int(pids[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int, nargs="?", help="PID of ApexCore.exe; auto-detected if omitted")
    parser.add_argument("--stdout", action="store_true", help="Write YAML to stdout without saving a file")
    args = parser.parse_args()
    try:
        pid = args.pid if args.pid is not None else find_pid()
        config = qingyunti_geodata(extract(pid), pid=pid)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"提取失败：{error}\n")
    target = Path(__file__).resolve().with_name("qingyunti-clash.yaml")
    text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    assert yaml.safe_load(text) == config
    if args.stdout:
        sys.stdout.write(text)
        return
    target.write_text(text, encoding="utf-8")
    print(f"Exported {len(config['proxies'])} nodes to {target}")


if __name__ == "__main__":
    main()
