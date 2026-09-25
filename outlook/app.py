"""Perspectives의 첫 수직 기능: 관측 탐색, 가설 선택, 스냅샷 저장."""
from __future__ import annotations

import secrets
from collections import OrderedDict
from copy import deepcopy
from datetime import date
from pathlib import Path
from threading import Lock
from time import monotonic

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import SecurityError

from outlook.catalog import AXIS_BY_ID
from outlook.evidence import build_evidence, read_observations
from outlook.store import SnapshotStore

ROOT = Path(__file__).resolve().parents[1]


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=secrets.token_hex(32),
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
        MAX_CONTENT_LENGTH=32_768, MAX_FORM_MEMORY_SIZE=16_384, MAX_FORM_PARTS=30,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
        SNAPSHOT_DIR=ROOT / "data" / "outlook" / "perspectives",
        OBSERVATION_READER=read_observations, TODAY=date.today,
    )
    if test_config:
        app.config.update(test_config)
    snapshots = SnapshotStore(Path(app.config["SNAPSHOT_DIR"]))
    cache, drafts = OrderedDict(), OrderedDict()
    cache_lock, draft_lock = Lock(), Lock()

    def evidence_for(cutoff: date) -> dict:
        with cache_lock:
            cached = cache.get(cutoff)
            if cached and monotonic() - cached[0] < 120:
                return deepcopy(cached[1])
            try:
                observations = app.config["OBSERVATION_READER"](cutoff)
                evidence = build_evidence(cutoff, observations)
            except Exception as error:
                # 예외 메시지/DSN/운영 행은 로그에 남기지 않는다.
                app.logger.warning("Observation query unavailable (%s)", type(error).__name__)
                return build_evidence(cutoff, [], error=True)
            cache[cutoff] = (monotonic(), evidence)
            while len(cache) > 16:
                cache.popitem(last=False)
            return deepcopy(evidence)

    @app.before_request
    def csrf_protection():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)
        if request.method == "POST":
            supplied = request.form.get("csrf", "")
            if not secrets.compare_digest(supplied.encode("utf-8"), session["csrf"].encode("utf-8")):
                abort(400, description="Your form expired. Reopen Perspectives and try again.")

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.template_filter("number")
    def number(value):
        return f"{value:,.2f}".rstrip("0").rstrip(".") if value is not None else "—"

    def page(evidence: dict, saved=None):
        axes = evidence["axes"]
        axis_id = request.args.get("axis", axes[0]["id"])
        axis = next((item for item in axes if item["id"] == axis_id), None)
        if axis is None:
            abort(404, description="This axis does not exist in this perspective.")
        draft_id = None
        if saved is None:
            draft_id = secrets.token_hex(24)
            with draft_lock:
                drafts[draft_id] = (monotonic(), session["csrf"], deepcopy(evidence))
                while len(drafts) > 128:
                    drafts.popitem(last=False)
        try:
            recent, unreadable = snapshots.recent()
        except OSError:
            recent, unreadable = [], 1
        return render_template(
            "perspectives.html", evidence=evidence, axis=axis,
            saved=saved, recent=recent, unreadable=unreadable,
            draft_id=draft_id, today=app.config["TODAY"]().isoformat(),
            selected=saved["selected_axes"] if saved else [],
        )

    @app.get("/")
    def index():
        return redirect(url_for("perspectives"))

    @app.get("/perspectives")
    def perspectives():
        today = app.config["TODAY"]()
        try:
            cutoff = date.fromisoformat(request.args.get("as_of", today.isoformat()))
        except ValueError:
            abort(400, description="Choose a valid cutoff date.")
        if cutoff < date(1980, 1, 1) or cutoff > today:
            abort(400, description="Choose a cutoff between 1980-01-01 and today.")
        return page(evidence_for(cutoff))

    @app.post("/perspectives/save")
    def save():
        name = request.form.get("name", "").strip()
        note = request.form.get("note", "").strip()
        selected = list(dict.fromkeys(request.form.getlist("axes")))
        if not name or len(name) > 100 or len(note) > 3000:
            abort(400, description="Use a name up to 100 characters and notes up to 3,000 characters.")
        if not selected or any(axis not in AXIS_BY_ID for axis in selected):
            abort(400, description="Select at least one valid axis to save.")
        draft_id = request.form.get("draft_id", "")
        with draft_lock:
            draft = drafts.get(draft_id)
            if not draft or monotonic() - draft[0] > 3600 or draft[1] != session["csrf"]:
                abort(400, description="This view expired. Reopen Perspectives before saving.")
            evidence = deepcopy(draft[2])
        if evidence["status"] == "unavailable":
            abort(400, description="Reconnect to the observations before saving this view.")
        try:
            identifier = snapshots.save(evidence, name, selected, note)
        except OSError:
            app.logger.warning("Local perspective could not be saved")
            abort(503, description="Local storage is unavailable. Your perspective was not saved.")
        flash("Perspective saved with the observations shown in your view.")
        return redirect(url_for("saved_perspective", identifier=identifier), code=303)

    @app.get("/perspectives/saved/<identifier>")
    def saved_perspective(identifier: str):
        try:
            saved = snapshots.get(identifier)
        except FileNotFoundError:
            abort(404, description="This saved perspective was not found.")
        except (ValueError, KeyError, TypeError):
            abort(404, description="This perspective could not be read.")
        except OSError:
            abort(503, description="Local perspective storage is unavailable.")
        return page(saved["evidence"], saved)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(503)
    def error_page(error):
        if isinstance(error, SecurityError):
            # 신뢰할 수 없는 Host에서는 URL 어댑터가 생성되지 않는다.
            return "Untrusted host", 400, {"Content-Type": "text/plain; charset=utf-8"}
        return render_template("error.html", error=error), error.code

    return app
