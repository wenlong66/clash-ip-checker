"""Export a loaded ApexCore Clash config without writing a memory dump."""
import argparse
import copy
import ctypes as c
import ctypes.wintypes as w
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

APEX_CORE = Path(r"D:\Program Files (x86)\青云梯-极速版\ApexCore.exe")
RUNTIME_FIELDS = (
    "mixed-port", "port", "socks-port", "redir-port", "tproxy-port",
    "external-controller", "secret", "tun", "interface-name", "auto-detect-interface",
)


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


def portable_config(config):
    result = copy.deepcopy(config)
    for field in RUNTIME_FIELDS:
        result.pop(field, None)
    if isinstance(result.get("dns"), dict):
        result["dns"]["proxy-server-nameserver"] = ["system"]
    return result


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
            # shortcut: requires intact null-delimited config in one region; revisit after client layout changes.
            for match in re.finditer(rb'(?m)^proxies\s*:|"proxies"\s*:\s*\[', raw):
                start = raw.rfind(b"\0", max(0, match.start() - 2_000_000), match.start()) + 1
                end = raw.find(b"\0", match.end(), min(len(raw), match.end() + 2_000_000))
                if end < 0:
                    continue
                config = parse_config(raw[start:end])
                if config and (found is None or len(config["proxies"]) > len(found["proxies"])):
                    found = config
    finally:
        kernel.CloseHandle(handle)
    if found is None:
        raise RuntimeError("No complete config found; keep Apex connected and retry, or recheck client version")
    return portable_config(found)


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
        config = extract(args.pid if args.pid is not None else find_pid())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
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
