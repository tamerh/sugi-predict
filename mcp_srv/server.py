"""BioYoda substrate server — FastAPI REST + MCP, dual-mode.

    python -m mcp_srv --mode http     # REST + MCP-over-HTTP on :8011 (remote)
    python -m mcp_srv --mode stdio    # local MCP for Claude CLI (default)
"""
import logging
import sys
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import config
from . import engine as E


def setup_logging():
    config.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    console = logging.StreamHandler(sys.stderr); console.setFormatter(logging.Formatter(fmt))
    fileh = RotatingFileHandler(config.log_file, maxBytes=10*1024*1024, backupCount=5); fileh.setFormatter(logging.Formatter(fmt))
    logging.basicConfig(level=getattr(logging, config.log_level), handlers=[console, fileh])
    al = logging.getLogger("access")
    ah = RotatingFileHandler(config.access_log_file, maxBytes=10*1024*1024, backupCount=5)
    ah.setFormatter(logging.Formatter("%(asctime)s %(message)s")); al.addHandler(ah); al.setLevel(logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)
access_logger = logging.getLogger("access")


def get_client_ip(request: Request) -> str:
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP")
            or (request.client.host if request.client else "unknown"))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t = time.perf_counter()
        resp = await call_next(request)
        if config.log_requests:
            q = f"?{request.url.query}" if request.url.query else ""
            access_logger.info(f"{get_client_ip(request)} {request.method} {request.url.path}{q} "
                               f"{resp.status_code} {(time.perf_counter()-t)*1000:.1f}ms")
        return resp


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting BioYoda server on {config.host}:{config.port}; Qdrant {config.qdrant_url}")
    try:
        E.qc().get_collections()
        logger.info("Qdrant connection verified")
    except Exception as e:
        logger.warning(f"Could not reach Qdrant: {e}")
    yield
    logger.info("Server shutdown complete")


app = FastAPI(title="BioYoda Substrate Server",
              description="REST + MCP over the BioYoda multi-modal collections + chemical target engine",
              version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["https://sugi.bio", "https://www.sugi.bio", "https://dev.sugi.bio", "http://localhost:3000"],
    allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
app.add_middleware(RequestLoggingMiddleware)

from .api import router as api_router
from .mcp_handlers import router as mcp_router
app.include_router(api_router)
app.include_router(mcp_router)


@app.get("/health")
async def health_check():
    try:
        n = len(E.qc().get_collections().collections)
        return {"status": "healthy", "qdrant": "connected", "collections": n}
    except Exception:
        return {"status": "degraded", "qdrant": "disconnected"}


def run_http_server():
    import uvicorn
    uvicorn.run("mcp_srv.server:app", host=config.host, port=config.port, log_level=config.log_level.lower())


def main():
    import argparse
    p = argparse.ArgumentParser(description="BioYoda Substrate Server")
    p.add_argument("--mode", choices=["http", "stdio"], default="stdio")
    args = p.parse_args()
    if args.mode == "http":
        run_http_server()
    else:
        import asyncio
        from .mcp_handlers import run_stdio_server
        asyncio.run(run_stdio_server())
