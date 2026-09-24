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

from backend.experiments.structured_playground import runner, simple
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
    ui_state: Optional[Dict[str, Any]] = None      # the recruiter page's own state, saved so a search can be reused


class SimpleBuildRequest(BaseModel):
    state: Dict[str, Any]


class SimpleRunRequest(BaseModel):
    state: Dict[str, Any]
    limit: int = 10
    confirm_unavailable: bool = False


def _friendly(state: Dict[str, Any]) -> Dict[str, List[str]]:
    """Recruiter-language cautions about the filters in use (never changes the query)."""
    used: List[Dict[str, Any]] = []

    def walk(items: List[Dict[str, Any]]) -> None:
        for item in items:
            if item.get("type") == "group":
                walk(item.get("items") or [])
            elif item.get("filter") in simple.BY_ID:
                used.append(simple.BY_ID[item["filter"]])

    walk(state.get("items") or [])
    payload = {f["id"]: f for f in simple.filters_payload()}
    unavailable = [f["label"] for f in used if payload[f["id"]]["status"] == "unavailable"]
    untested = [f["label"] for f in used if payload[f["id"]]["status"] == "documented_unverified"]
    warnings = [f"“{label}” is not available on our CrustData plan. The search can still be sent, but it may return nothing useful." for label in dict.fromkeys(unavailable)]
    notes = []
    if untested:
        notes.append("Not tested yet on our account: " + ", ".join(dict.fromkeys(untested)) + ". They are part of CrustData's search but we have not confirmed how they behave for us.")
    return {"warnings": warnings, "notes": notes}


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

    def page(name: str) -> str:
        return (STATIC / name).read_text(encoding="utf-8").replace("__PLAYGROUND_TOKEN__", token)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page("simple.html")          # recruiter view

    @app.get("/advanced", response_class=HTMLResponse)
    def advanced() -> str:
        return page("index.html")           # full operator-level builder

    def execute(tree: Dict[str, Any], limit: int, fields: Optional[List[str]], confirm: bool, ui_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        built = build(tree)
        if not built["ok"]:
            raise HTTPException(422, {"message": "The query has errors and was not sent.", "errors": built["errors"]})
        unavailable = [w for w in built["warnings"] if "UNAVAILABLE" in w["message"]]
        if unavailable and not confirm:
            raise HTTPException(409, {"message": "The search uses something that is not available on our CrustData plan. Send it anyway?", "warnings": unavailable})
        try:
            context = {"tree": tree, "boolean_text": built["boolean_text"], "warnings": built["warnings"], "ui_state": ui_state}
            return {"built": built, **runner.run(built["filters"], limit, fields, client=client, context=context)}
        except runner.RunError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/catalog", dependencies=[Depends(guard)])
    def catalog() -> Dict[str, Any]:
        return {**catalog_payload(), "projectable_fields": runner.PROJECTABLE_FIELDS, "default_fields": runner.DEFAULT_FIELDS,
                "max_limit": runner.MAX_LIMIT, "credits_per_result": runner.CREDITS_PER_RESULT}

    @app.post("/api/build", dependencies=[Depends(guard)])
    def build_endpoint(req: BuildRequest) -> Dict[str, Any]:
        return build(req.tree)

    @app.post("/api/run", dependencies=[Depends(guard)])
    def run_endpoint(req: RunRequest) -> Dict[str, Any]:
        return execute(req.tree, req.limit, req.fields, req.confirm_unavailable, req.ui_state)

    @app.get("/api/simple/filters", dependencies=[Depends(guard)])
    def simple_filters() -> Dict[str, Any]:
        return {"filters": simple.filters_payload(), "max_limit": runner.MAX_LIMIT, "credits_per_result": runner.CREDITS_PER_RESULT}

    @app.post("/api/simple/build", dependencies=[Depends(guard)])
    def simple_build(req: SimpleBuildRequest) -> Dict[str, Any]:
        tree, problems = simple.to_tree(req.state)
        result: Dict[str, Any] = {"ok": False, "problems": problems, "text": simple.to_text(req.state), "tree": tree, "technical": None, **_friendly(req.state)}
        if tree is not None:
            built = build(tree)
            result["technical"] = built
            result["ok"] = built["ok"]
            if not built["ok"]:
                result["problems"] = [e["message"] for e in built["errors"]]
        return result

    @app.post("/api/simple/run", dependencies=[Depends(guard)])
    def simple_run(req: SimpleRunRequest) -> Dict[str, Any]:
        tree, problems = simple.to_tree(req.state)
        if tree is None:
            raise HTTPException(422, {"message": "The search is not complete.", "errors": [{"message": p} for p in problems]})
        return execute(tree, req.limit, None, req.confirm_unavailable, req.state)

    @app.get("/api/runs", dependencies=[Depends(guard)])
    def runs() -> List[Dict[str, Any]]:
        return runner.list_runs()

    @app.get("/api/runs/{run_id}", dependencies=[Depends(guard)])
    def run_detail(run_id: str) -> Dict[str, Any]:
        try:
            return runner.load_run(run_id)
        except runner.RunError as exc:
            raise HTTPException(404, str(exc))

    return app


def main() -> None:
    import uvicorn

    app = create_app()
    print(f"CrustData Structured Search Playground: http://{HOST}:{PORT}   (local only; runs spend CrustData credits)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
