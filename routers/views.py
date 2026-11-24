from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

project_dir = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=project_dir / "templates")
templates.env.globals["app_js_version"] = sha256((project_dir / "static/js/app.js").read_bytes()).hexdigest()[:12]

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render main page"""
    return templates.TemplateResponse(request=request, name="index.html", context={"page": "check"})


@router.get("/failover", response_class=HTMLResponse)
async def failover(request: Request):
    """Render the independent failover configuration page."""
    return templates.TemplateResponse(request=request, name="index.html", context={"page": "failover"})


@router.get("/qingyunti", response_class=HTMLResponse)
async def qingyunti(request: Request):
    """Render the local Qingyunti export page."""
    return templates.TemplateResponse(request=request, name="index.html", context={"page": "qingyunti"})
