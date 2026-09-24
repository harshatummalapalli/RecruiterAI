"""Standalone local server for the Structured Search Playground.

    python -m backend.experiments.structured_playground          # http://127.0.0.1:8765

It is a separate FastAPI app, bound to loopback, that never imports or mounts into the production app, never
touches the SearchStore, and is never deployed. Because /api/run can spend CrustData credits, every request must
carry the per-launch token embedded in the page it serves (blocks a random web page from posting to localhost)."""

import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.experiments.structured_playground import runner
from backend.experiments.structured_playground.builder import build
from backend.experiments.structured_playground.catalog import catalog_payload

STATIC = Path(__file__).parent / "static"
HOST, PORT = "127.0.0.1", 8765


class BuildRequest(BaseModel):
    tree: Dict[str, Any]


class RunRequest(BaseModel):
    tree: Dict[str, Any]
    limit: int = 10
    fields: Optional[List[str]] = None
    confirm_unavailable: bool = False


def create_app(token: Optional[str] = None, client: Any = None) -> FastAPI:
    token = token or secrets.token_urlsafe(24)
    app = FastAPI(title="CrustData Structured Search Playground", docs_url=None, redoc_url=None)
    app.state.token = token

    def guard(request: Request, x_playground_token: Optional[str] = Header(default=None)) -> None:
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            raise HTTPException(403, "Loopback only.")
        if not secrets.compare_digest(x_playground_token or "", token):
            raise HTTPException(403, "Missing or wrong playground token.")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8").replace("__PLAYGROUND_TOKEN__", token)

    @app.get("/api/catalog", dependencies=[Depends(guard)])
    def catalog() -> Dict[str, Any]:
        return {**catalog_payload(), "projectable_fields": runner.PROJECTABLE_FIELDS, "default_fields": runner.DEFAULT_FIELDS,
                "max_limit": runner.MAX_LIMIT, "credits_per_result": runner.CREDITS_PER_RESULT}

    @app.post("/api/build", dependencies=[Depends(guard)])
    def build_endpoint(req: BuildRequest) -> Dict[str, Any]:
        return build(req.tree)

    @app.post("/api/run", dependencies=[Depends(guard)])
    def run_endpoint(req: RunRequest) -> Dict[str, Any]:
        built = build(req.tree)
        if not built["ok"]:
            raise HTTPException(422, {"message": "The query has errors and was not sent.", "errors": built["errors"]})
        unavailable = [w for w in built["warnings"] if "UNAVAILABLE" in w["message"]]
        if unavailable and not req.confirm_unavailable:
            raise HTTPException(409, {"message": "The query uses field(s) marked UNAVAILABLE for our account. Confirm to send it anyway.", "warnings": unavailable})
        try:
            return {"built": built, **runner.run(built["filters"], req.limit, req.fields, client=client)}
        except runner.RunError as exc:
            raise HTTPException(400, str(exc))

    return app


def main() -> None:
    import uvicorn

    app = create_app()
    print(f"CrustData Structured Search Playground: http://{HOST}:{PORT}   (local only; runs spend CrustData credits)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
