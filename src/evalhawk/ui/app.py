"""The local web app: runs dashboard, blind labelling, judge report cards.

Install with ``pip install "evalhawk[ui]"`` and start with ``evalhawk ui``. It binds to
127.0.0.1 by default and rejects cross-site form posts, so another website open in the
browser cannot submit labels.
"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from evalhawk.core.errors import DataError, EvalhawkError
from evalhawk.core.models import Outcome
from evalhawk.core.splits import SplitSet
from evalhawk.services.calibrate import calibration_status
from evalhawk.services.estimate import report as estimate_report
from evalhawk.services.evaluate import judged_rates
from evalhawk.services.labeling import criterion_entry, queue, save_label
from evalhawk.wiring import open_store

HERE = Path(__file__).parent


def _pretty(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def create_app(db: Path, *, annotator: str, seed: int = 0) -> FastAPI:
    """Build the app for one database and one annotator name."""
    app = FastAPI(title="EvalHawk", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.filters["pretty"] = _pretty
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next: Any) -> Response:
        if request.method == "POST":
            origin = request.headers.get("origin") or request.headers.get("referer")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return Response("cross-site request refused", status_code=403)
        return await call_next(request)

    def page(request: Request, name: str, **context: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"annotator": annotator, **context})

    @app.exception_handler(EvalhawkError)
    async def evalhawk_error(request: Request, exc: EvalhawkError) -> HTMLResponse:
        return page(request, "error.html", message=str(exc))

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        with open_store(db) as store:
            runs = store.list_runs()
        return page(request, "index.html", runs=runs)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: str) -> HTMLResponse:
        with open_store(db) as store:
            run = store.get_run(run_id)
            if run is None:
                raise DataError(f"no run {run_id}")
            splits = SplitSet.model_validate(run.config_snapshot["splits"])
            rates = {(r.criterion, r.judge): r for r in judged_rates(store, run, splits.id)}
            statuses = calibration_status(store, run, splits.id)
        rows = [(status, rates.get((status.criterion, status.judge))) for status in statuses]
        return page(request, "run.html", run=run, rows=rows)

    def _label_state(run_id: str, criterion: str) -> dict[str, Any]:
        with open_store(db) as store:
            run = store.get_run(run_id)
            if run is None:
                raise DataError(f"no run {run_id}")
            state = queue(store, run, criterion, annotator=annotator, seed=seed)
        return {"run": run, "criterion_name": criterion, "state": state}

    @app.get("/label/{run_id}/{criterion}", response_class=HTMLResponse)
    def label_page(request: Request, run_id: str, criterion: str) -> HTMLResponse:
        return page(request, "label.html", **_label_state(run_id, criterion))

    @app.post("/label/{run_id}/{criterion}", response_class=HTMLResponse)
    async def label_submit(request: Request, run_id: str, criterion: str) -> Response:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8")).items()}
        try:
            outcome = Outcome(form.get("outcome", ""))
        except ValueError:
            return Response("outcome must be PASS, FAIL or UNKNOWN", status_code=400)
        with open_store(db) as store:
            run = store.get_run(run_id)
            if run is None:
                raise DataError(f"no run {run_id}")
            save_label(
                store,
                trace_id=form.get("trace_id", ""),
                criterion_id=criterion_entry(run, criterion)["criterion_id"],
                annotator=annotator,
                outcome=outcome,
                note=form.get("note"),
            )
        if request.headers.get("hx-request"):
            return page(request, "_item.html", **_label_state(run_id, criterion))
        return RedirectResponse(f"/label/{run_id}/{criterion}", status_code=303)

    @app.get("/report/{run_id}/{criterion}", response_class=HTMLResponse)
    def report_page(
        request: Request, run_id: str, criterion: str, judge: str | None = None
    ) -> HTMLResponse:
        with open_store(db) as store:
            run = store.get_run(run_id)
            if run is None:
                raise DataError(f"no run {run_id}")
            splits = SplitSet.model_validate(run.config_snapshot["splits"])
            entry = criterion_entry(run, criterion)
            if judge is not None:
                matches = [
                    e
                    for e in calibration_status(store, run, splits.id)
                    if e.criterion == criterion and e.judge == judge
                ]
                if matches:
                    entry = {**entry, "judge": judge, "judge_id": matches[0].judge_id}
            try:
                result = estimate_report(
                    store,
                    run_id=run.id,
                    criterion_id=entry["criterion_id"],
                    judge_id=entry["judge_id"],
                    split_set_id=splits.id,
                    rng=np.random.default_rng(seed),
                )
                problem = None
            except (DataError, EvalhawkError) as exc:
                result, problem = None, str(exc)
        return page(
            request,
            "report.html",
            run=run,
            criterion_name=criterion,
            entry=entry,
            result=result,
            problem=problem,
        )

    return app
