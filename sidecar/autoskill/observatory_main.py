from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette import status as http_status

from autoskill.api.app import create_app


def create_observatory_app(static_root: Path | None = None):
    app = create_app(api_surface="observatory")
    root = static_root or Path(
        os.environ.get("SKILLKERNEL_OBSERVATORY_STATIC_ROOT", "/app/observatory")
    )
    index = root / "index.html"

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> PlainTextResponse:
        return PlainTextResponse("ok\n")

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/admin/assets", StaticFiles(directory=assets), name="observatory-assets")

    async def _index() -> FileResponse:
        if not index.is_file():
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Observatory static assets are unavailable",
            )
        return FileResponse(index)

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/", include_in_schema=False)
    async def observatory_index() -> FileResponse:
        return await _index()

    @app.get("/admin/{_spa_path:path}", include_in_schema=False)
    async def observatory_spa(_spa_path: str) -> FileResponse:
        if _spa_path == "api" or _spa_path.startswith("api/"):
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND)
        return await _index()

    return app


app = create_observatory_app()
