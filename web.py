"""
Clash IP Checker - Web Configuration Interface
FastAPI backend with SSE progress and REST API
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routers.api import router as api_router
from routers.views import router as views_router
from routers.failover import router as failover_router
from routers.qingyunti import router as qingyunti_router

from contextlib import asynccontextmanager
from state import state
from utils.network import lan_ip, require_download, require_local

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Legacy Windows console encodings must not make emoji node names abort checks.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    yield
    # Shutdown
    print("[Web] Shutting down, cleaning up resources...")
    await state.checker.stop()

app = FastAPI(title="Clash IP Checker", lifespan=lifespan)


@app.middleware("http")
async def restrict_lan_access(request: Request, call_next):
    try:
        if request.method in {"GET", "HEAD"} and (
                request.url.path.startswith("/exports/") or request.url.path.startswith("/api/qingyunti/download/")):
            require_download(request)
        else:
            require_local(request)
    except HTTPException as error:
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)
    return await call_next(request)

# Mount supporting static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Ensure exports directory
exports_dir = "exports"
os.makedirs(exports_dir, exist_ok=True)
app.mount("/exports", StaticFiles(directory=exports_dir), name="exports")

# Include Routers
app.include_router(views_router)
app.include_router(api_router)
app.include_router(failover_router)
app.include_router(qingyunti_router)

if __name__ == "__main__":
    import uvicorn
    address = lan_ip()
    print(f"[Web] LAN subscription base: http://{address}:18080" if address else "[Web] LAN IP unavailable; YAML download remains available")
    uvicorn.run(app, host="0.0.0.0", port=18080, proxy_headers=False)
