"""Invoke the native subscription refresh and verify Clash saved the export."""
import os
from pathlib import Path
import subprocess
import time

from fastapi import HTTPException

SCRIPT = Path(__file__).with_name('refresh_clash_subscription.ps1').resolve()
WINDOW_TIMEOUT = 15
SAVE_TIMEOUT = 20


def refresh_subscription(name: str, profile_path: Path, export_path: Path):
    if os.name != 'nt':
        raise HTTPException(status_code=400, detail='请在 Clash Verge Rev 所在的 Windows 桌面运行网页服务')
    try:
        expected = export_path.read_text(encoding='utf-8-sig')
        before = profile_path.stat().st_mtime_ns if profile_path.exists() else None
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(SCRIPT)],
            env={**os.environ, 'CLASH_REFRESH_PROFILE': name}, timeout=WINDOW_TIMEOUT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='Clash 窗口未及时响应，无法确认订阅是否已更新') from None
    except (OSError, UnicodeError):
        raise HTTPException(status_code=500, detail='无法读取配置或启动 Windows 订阅更新，请检查本机权限') from None
    if result.returncode == 10:
        raise HTTPException(status_code=409, detail='请先在同一个 Windows 用户下运行 Clash Verge Rev')
    if result.returncode:
        raise HTTPException(status_code=409, detail='未能调用目标订阅的刷新按钮，请检查 Clash 是否有弹窗、订阅是否正在更新或界面是否兼容')

    deadline = time.monotonic() + SAVE_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if profile_path.stat().st_mtime_ns != before and profile_path.read_text(encoding='utf-8-sig') == expected:
                return
        except (OSError, UnicodeError):
            pass  # Clash may still be replacing its local copy.
        time.sleep(0.25)
    raise HTTPException(status_code=504, detail='未能确认 Clash 已保存新配置，请查看 Clash 的更新提示后重试')
