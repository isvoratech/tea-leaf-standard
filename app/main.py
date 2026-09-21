"""Leaf Standard module for Field Diary.

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8015
Apache proxies  /field-diary/leaf-standard/  ->  http://127.0.0.1:8015/
All front-end URLs are relative, so any prefix works.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import init_db
from .router import router

STATIC = config.BASE_DIR / "static"

@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(lifespan=lifespan, title="Field Diary - Leaf Standard", docs_url="/api/docs", openapi_url="/api/openapi.json")
if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET"],
                       allow_headers=["Authorization", "X-Embed-Key"])
app.include_router(router)


@app.middleware("http")
async def headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.url.path.startswith("/embed"):
        anc = " ".join(["'self'"] + config.CORS_ORIGINS)
        resp.headers["Content-Security-Policy"] = f"frame-ancestors {anc}"
    else:
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.url.path.endswith((".html", ".js", "/")) or "." not in request.url.path.rsplit("/", 1)[-1]:
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def _page(name):
    return lambda: FileResponse(STATIC / name)


app.add_api_route("/", _page("index.html"), include_in_schema=False)
app.add_api_route("/dashboard", _page("dashboard.html"), include_in_schema=False)
app.add_api_route("/admin", _page("admin.html"), include_in_schema=False)
app.add_api_route("/embed", _page("embed.html"), include_in_schema=False)
app.add_api_route("/health", lambda: {"ok": True}, include_in_schema=False)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.add_api_route("/sw.js", _page("sw.js"), include_in_schema=False)
app.add_api_route("/manifest.json", _page("manifest.json"), include_in_schema=False)
