"""Save generated subscriptions without truncating an existing export on failure."""
from pathlib import Path
import uuid

from fastapi import HTTPException


def save_export(directory, filename, content):
    directory = Path(directory)
    temporary = directory / f"{uuid.uuid4().hex}.tmp"
    try:
        directory.mkdir(exist_ok=True)
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(directory / filename)
    except OSError:
        raise HTTPException(status_code=500, detail="保存配置失败，原订阅源保持不变，请检查目录写入权限") from None
    finally:
        temporary.unlink(missing_ok=True)
