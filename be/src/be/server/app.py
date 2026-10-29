"""The FastAPI app `be server` runs: the JSON API, and the built web app for every other path."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from be.server import mcp
from be.server.api import ActionFailed, State, router

log = logging.getLogger(__name__)

# where `pnpm build` in be/web puts the app
STATIC = Path(__file__).parent / "static"

MISSING = "the web app isn't built; run `pnpm -C be/web install && pnpm -C be/web build`, or `python configure.py`"


def create_app(state: State | None = None, static: Path | None = STATIC, host: str = "127.0.0.1") -> FastAPI:
    """static is the built web app to serve, or None to serve only the API (as with --dev, where Vite
    serves the app); host is the address the server listens on, which /mcp checks requests' Host against
    when it's local."""
    todos = mcp.build()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with todos.session_manager.run():
            yield

    app = FastAPI(
        title="be", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan
    )
    app.state.be = state or State()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        query = f"?{request.url.query}" if request.url.query else ""
        log.info(
            "%s %s%s %d (%.0f ms)",
            request.method,
            request.url.path,
            query,
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response

    @app.exception_handler(ActionFailed)
    async def action_failed(request: Request, exc: ActionFailed):
        return JSONResponse({"message": str(exc)}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # the app reads "message" for every error
        if request.url.path.startswith("/api"):
            return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def bad_input(request: Request, exc: RequestValidationError):
        problems = "; ".join(f"{'.'.join(map(str, e['loc'][1:]))}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"message": problems or "bad input"}, status_code=400)

    app.include_router(router)
    # before the web app's catch-all route, which would otherwise answer /mcp
    app.router.routes.extend(mcp.routes(todos, host))

    if static is not None:

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            """A built file if there is one, else index.html, so the app's own routes load on reload."""
            if path.startswith("api/"):
                raise HTTPException(404, f"no route /{path}")
            index = static / "index.html"
            if not index.is_file():
                return PlainTextResponse(MISSING, status_code=503)
            found = (static / path).resolve()
            if path and found.is_file() and found.is_relative_to(static.resolve()):
                return FileResponse(found)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
