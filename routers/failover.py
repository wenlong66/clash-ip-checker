"""Build a standalone failover profile from local Clash Verge subscriptions."""
import copy
import io
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from ruamel.yaml import YAML, YAMLError

from schemas import FailoverRequest
from utils.exports import save_export


def require_local(request: Request):
    local_hosts = {"127.0.0.1", "::1", "localhost"}
    if not request.client or request.client.host not in local_hosts or request.url.hostname not in local_hosts:
        raise HTTPException(status_code=403, detail="请通过本机 localhost 或 127.0.0.1 打开网页")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail="仅允许当前网页读取本机订阅")


router = APIRouter(prefix="/api/failover", dependencies=[Depends(require_local)])
SKIP_KEYWORDS = ("剩余", "重置", "到期", "有效期", "官网", "网址", "更新", "公告", "建议")


def profile_directory():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise HTTPException(status_code=404, detail="此功能需要在安装 Clash Verge Rev 的 Windows 电脑上运行")
    return Path(appdata) / "io.github.clash-verge-rev.clash-verge-rev"


def read_yaml(path):
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, YAMLError):
        raise ValueError("配置文件无法读取，请先在 Clash Verge Rev 中更新该订阅") from None
    if not isinstance(data, dict):
        raise ValueError("配置文件不是有效的 Clash YAML")
    return data


def local_profiles():
    root = profile_directory()
    try:
        items = read_yaml(root / "profiles.yaml").get("items", [])
    except ValueError as error:
        raise HTTPException(status_code=404, detail="未能读取本机 Clash Verge Rev 订阅，请以同一 Windows 用户运行网页服务") from error
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Clash Verge Rev 订阅索引格式错误")
    return root, [item for item in items if isinstance(item, dict) and item.get("type") in ("local", "remote")]


def profile_nodes(root, profile):
    directory = (root / "profiles").resolve()
    filename = profile.get("file")
    if not isinstance(filename, str):
        raise ValueError("订阅缺少本机配置文件")
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory):
        raise ValueError("订阅文件必须位于 Clash Verge Rev 的 profiles 目录中")
    proxies = read_yaml(path).get("proxies", [])
    if not isinstance(proxies, list):
        raise ValueError("订阅的 proxies 格式错误")
    nodes = [proxy for proxy in proxies if isinstance(proxy, dict)
             and isinstance(proxy.get("name"), str) and proxy["name"].strip()
             and proxy.get("type") and proxy.get("server")
             and not any(word in proxy["name"] for word in SKIP_KEYWORDS)]
    if len({node["name"] for node in nodes}) != len(nodes):
        raise ValueError("订阅包含重名节点，请先在 Clash Verge Rev 中区分节点名称")
    return nodes


def exported_profile_filename(profile, http_request, kind="failover"):
    """Only this web app's existing generated subscriptions can be updated."""
    try:
        url = urlsplit(profile.get("url") or "")
        if (profile.get("type") != "remote" or url.scheme != http_request.url.scheme
                or url.hostname not in {"127.0.0.1", "::1", "localhost"}
                or url.port != http_request.url.port or url.fragment):
            return None
    except ValueError:
        return None
    patterns = {
        "failover": r"/exports/(clash_failover_[0-9a-f]{32}\.yaml)",
        "checked": r"/exports/(clash_checked_(?:[0-9a-f]{8}|[0-9a-f]{32})\.yaml)",
        "qingyunti": r"/api/qingyunti/download/([0-9a-f]{32})",
    }
    match = re.fullmatch(patterns[kind], url.path)
    if match:
        filename = f"qingyunti_{match[1]}.yaml" if kind == "qingyunti" else match[1]
        directory = "private_exports" if kind == "qingyunti" else "exports"
        if (Path(directory) / filename).is_file():
            return filename
    return None


def export_target(target_profile_id, http_request, kind):
    if not target_profile_id:
        return None, None
    require_local(http_request)
    _, profiles = local_profiles()
    target = next((item for item in profiles if item.get("uid") == target_profile_id), None)
    filename = exported_profile_filename(target, http_request, kind) if target else None
    if not filename:
        raise HTTPException(status_code=400, detail="只能更新当前页生成且导出文件仍存在的配置，请刷新订阅列表")
    return filename, target.get("name") or target["uid"]


@router.get("/profiles")
def list_profiles(http_request: Request, kind: Literal["failover", "checked", "qingyunti"] = "failover"):
    root, profiles = local_profiles()
    result = []
    for profile in profiles:
        item = {"id": profile["uid"], "name": profile.get("name") or profile["uid"], "nodes": []}
        filename = exported_profile_filename(profile, http_request, kind)
        if filename:
            item["export_filename"] = filename
        try:
            item["nodes"] = [node["name"] for node in profile_nodes(root, profile)]
            if not item["nodes"]:
                item["error"] = "未找到独立节点；仅通过代理集合提供节点的订阅暂不支持"
        except ValueError as error:
            item["error"] = str(error)
        result.append(item)
    return {"profiles": result}


@router.post("/export")
def export_failover(request: FailoverRequest, http_request: Request):
    selections = [request.primary, request.backup]
    if request.backup2:
        selections.append(request.backup2)
    if len({(node.profile_id, node.node_name) for node in selections}) != len(selections):
        raise HTTPException(status_code=400, detail="主用和各备用请选择不同节点")
    root, profiles = local_profiles()
    target = None
    filename = None
    if request.target_profile_id:
        target = next((item for item in profiles if item.get("uid") == request.target_profile_id), None)
        filename = exported_profile_filename(target, http_request) if target else None
        if not filename:
            raise HTTPException(status_code=400, detail="只能更新本网页生成且导出文件仍存在的主备配置，请刷新订阅列表")
    proxies = []
    for role, selection in zip(("主用", "备用", "第二备用"), selections):
        profile = next((item for item in profiles if item.get("uid") == selection.profile_id), None)
        if profile is None:
            raise HTTPException(status_code=400, detail=f"{role}订阅已不存在，请刷新订阅列表")
        try:
            nodes = profile_nodes(root, profile)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=f"{role}订阅：{error}") from error
        node = next((node for node in nodes if node["name"] == selection.node_name), None)
        if node is None:
            raise HTTPException(status_code=400, detail=f"{role}节点已变化，请刷新订阅列表后重新选择")
        if node.get("dialer-proxy"):
            raise HTTPException(status_code=400, detail=f"{role}节点依赖链式代理，请选择独立节点")
        proxy = copy.deepcopy(node)
        proxy["name"] = f"{role} | {profile.get('name') or profile['uid']} | {node['name']}"
        proxies.append(proxy)

    group_names = ["主用节点", "备用节点", "备用节点2"][:len(proxies)]
    config = {
        "mode": "rule",
        "log-level": "info",
        # Proxifier may pass locally resolved IPs; recover TLS domains before routing.
        "sniffer": {
            "enable": True, "parse-pure-ip": True, "override-destination": True,
            "sniff": {"TLS": {"ports": [443, 8443]}},
        },
        "proxies": proxies,
        "proxy-groups": [
            {"name": "主备切换", "type": "fallback", "proxies": group_names,
             "url": "https://www.gstatic.com/generate_204", "interval": request.interval,
             "timeout": 5000, "lazy": False},
            *[{"name": name, "type": "select", "proxies": [proxy["name"]]}
              for name, proxy in zip(group_names, proxies)],
        ],
        "rule-providers": {
            name: {"type": "http", "behavior": behavior,
                   "url": f"https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/{name}.txt",
                   "path": f"./ruleset/loyalsoldier/{name}.yaml", "interval": 86400}
            for name, behavior in (
                ("private", "domain"), ("reject", "domain"),
                ("icloud", "domain"), ("apple", "domain"), ("google", "domain"),
                ("proxy", "domain"), ("direct", "domain"),
                ("lancidr", "ipcidr"), ("cncidr", "ipcidr"), ("telegramcidr", "ipcidr"),
            )
        },
        "rules": [
            "DOMAIN,clash.razord.top,DIRECT",
            "DOMAIN,yacd.haishan.me,DIRECT",
            "RULE-SET,private,DIRECT",
            "RULE-SET,reject,REJECT",
            "RULE-SET,icloud,DIRECT",
            "RULE-SET,apple,DIRECT",
            "RULE-SET,google,主备切换",
            "RULE-SET,proxy,主备切换",
            "RULE-SET,direct,DIRECT",
            "RULE-SET,lancidr,DIRECT",
            "RULE-SET,cncidr,DIRECT",
            "RULE-SET,telegramcidr,主备切换",
            "GEOIP,LAN,DIRECT",
            "GEOIP,CN,DIRECT",
            "MATCH,主备切换",
        ],
    }
    stream = io.StringIO()
    YAML().dump(config, stream)
    content = stream.getvalue()
    filename = filename or f"clash_failover_{uuid.uuid4().hex}.yaml"
    save_export("exports", filename, content)
    return {"yaml": content, "filename": filename, "url": f"/exports/{filename}", "failover": True,
            "updated_profile": (target.get("name") or target["uid"]) if target else None}
