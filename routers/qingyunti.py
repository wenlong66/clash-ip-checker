"""Export the local Qingyunti config using the existing isolated CLI."""
import os
import re
from pathlib import Path
import subprocess
import sys
from threading import Lock
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from ruamel.yaml import YAML, YAMLError

from routers.failover import export_target
from utils.exports import save_export
from utils.shadowrocket import shadowrocket_subscription
from utils.shadowrocket_rules import shadowrocket_rules_config
from utils.network import import_url, require_download, require_local
from utils.qingyunti_geodata import runtime_data_directory

router = APIRouter(prefix="/api/qingyunti")
export_lock = Lock()


@router.post("/export", dependencies=[Depends(require_local)])
def export_qingyunti(http_request: Request, target_profile_id: str = ''):
    if os.name != "nt":
        raise HTTPException(status_code=400, detail="请在安装梯子客户端的 Windows 电脑上运行网页服务")
    if not export_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="梯子配置正在提取中，请稍候")
    try:
        filename, updated_profile = export_target(target_profile_id, http_request, "qingyunti")
        script = Path(__file__).resolve().parents[1] / "qingyunti-export" / "extract.py"
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(script), "--stdout"],
                capture_output=True, text=True, encoding="utf-8", timeout=90,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="提取超时，请保持梯子客户端连接后重试") from None
        except OSError:
            raise HTTPException(status_code=500, detail="无法启动导出脚本，请检查 Python 运行环境") from None
        if result.returncode:
            error = result.stderr
            if "未找到 ApexCore" in error or "多个 ApexCore" in error:
                detail = "存在多个 ApexCore，请仅保留目标实例" if "多个 ApexCore" in error else "未找到 ApexCore，请启动梯子客户端并加载节点"
            elif "WinError 5" in error or "PermissionError" in error:
                detail = "没有读取梯子客户端的权限，请以同一 Windows 用户运行网页服务并检查进程权限"
            elif "PID does not belong" in error:
                detail = "梯子客户端安装路径与脚本不符，请核实并更新 utils/qingyunti_geodata.py 中的 APEX_CORE 路径"
            elif "活动连接" in error or "Get-NetTCPConnection" in error:
                detail = "请先在 Apex 连接一个节点并打开网页，保持连接后重新提取，以获取实际服务器地址"
            elif "活动节点地址" in error:
                detail = "无法读取或唯一匹配 Apex 节点地址，请保持客户端连接后重试；客户端升级后可能需要适配"
            elif "No module named" in error:
                detail = "导出依赖缺失，请安装 requirements.txt 中的依赖后重试"
            elif any(value in error for value in ('GeoSite', 'GeoIP', 'Geo 数据库', '数据目录', '内嵌规则集')):
                detail = "无法完整对齐青云梯规则数据库，请保持客户端运行后重新提取；缺失或不支持的 DNS／规则不会自动降级"
            else:
                detail = "未能提取完整配置，请保持梯子客户端连接后重试；客户端升级后可能需要适配"
            raise HTTPException(status_code=400, detail=detail)
        try:
            config = YAML(typ="safe").load(result.stdout)
        except YAMLError:
            config = None
        proxies = config.get("proxies") if isinstance(config, dict) else None
        if not isinstance(proxies, list) or not proxies:
            raise HTTPException(status_code=502, detail="导出脚本未返回有效节点配置，请重新提取")
        token = filename[len("qingyunti_"):-len(".yaml")] if filename else uuid.uuid4().hex
        filename = filename or f"qingyunti_{token}.yaml"
        save_export("private_exports", filename, result.stdout)
        return JSONResponse({"yaml": result.stdout, "node_count": len(proxies),
                             "filename": filename, "url": f"/api/qingyunti/download/{token}",
                             "import_url": import_url(http_request, f"/api/qingyunti/download/{token}"),
                             "export_kind": "qingyunti", "updated_profile": updated_profile,
                             "updated_profile_id": target_profile_id if updated_profile else None},
                            headers={"Cache-Control": "no-store"})
    finally:
        export_lock.release()


@router.get("/download/{token}", dependencies=[Depends(require_download)])
def download_qingyunti(token: str):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(status_code=404, detail="导出不存在，请在梯子导出页面重新提取")
    try:
        content = (Path("private_exports") / f"qingyunti_{token}.yaml").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="导出不存在，请在梯子导出页面重新提取") from None
    except OSError:
        raise HTTPException(status_code=500, detail="无法读取导出，请检查目录读取权限") from None
    return Response(content, media_type="application/yaml",
                    headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="qingyunti-clash.yaml"'})


@router.get("/download/{token}/shadowrocket.txt", dependencies=[Depends(require_local)])
def download_shadowrocket(token: str):
    return shadowrocket_download(token, rules_only=False)


@router.get("/download/{token}/shadowrocket-rules.conf", dependencies=[Depends(require_local)])
def download_shadowrocket_rules(token: str):
    return shadowrocket_download(token, rules_only=True)


def shadowrocket_download(token, rules_only):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(status_code=404, detail="导出不存在，请重新提取")
    try:
        source = (Path("private_exports") / f"qingyunti_{token}.yaml").read_text(encoding="utf-8")
        config = YAML(typ="safe").load(source)
        if rules_only:
            rules = config.get('rules') if isinstance(config, dict) else None
            needs_geosite = isinstance(rules, list) and any(isinstance(rule, str) and rule.startswith('GEOSITE,') for rule in rules)
            geosite_path = runtime_data_directory() / 'GeoSite.dat' if needs_geosite else None
            content = shadowrocket_rules_config(config, geosite_path)
        else:
            content = shadowrocket_subscription(config)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="导出不存在，请重新提取") from None
    except OSError:
        raise HTTPException(status_code=500, detail="无法读取导出，请检查本机文件权限") from None
    except YAMLError:
        raise HTTPException(status_code=400, detail="导出文件格式无效，请重新提取") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    filename = "qingyunti-shadowrocket-rules.conf" if rules_only else "qingyunti-shadowrocket.txt"
    return Response(content, media_type="text/plain", headers={
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="{filename}"',
    })
