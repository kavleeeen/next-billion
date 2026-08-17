"""A local viewer for everything the pipeline has collected.

Standard library only, no framework and no build step:

    GET  /                          the single-page UI
    GET  /api/search?q=&source=&sort=&limit=
    GET  /api/companies/{id}        detail: traction, founders, stories, comments, score
    POST /api/prepare               {ids: [...]} - threads + founders for a selection
    POST /api/score                 {ids: [...]} - five metrics and a verdict

Bound to 127.0.0.1 on purpose — this is a local viewer, not a service.
"""
from __future__ import annotations

import json
import logging
import re
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import ROOT, Settings, settings as default_settings
from .db import connect
from .prepare import MAX_SELECTION, TooManySelected, prepare
from .repository import analyses as analyses_repo
from .repository import companies as companies_repo
from .repository import founders as founders_repo
from .repository import github_repos as repos_repo
from .repository import hn_comments as comments_repo
from .repository import hn_stories as stories_repo
from .score import score
from .search import search

log = logging.getLogger(__name__)

INDEX_PATH = ROOT / "frontend" / "index.html"
DEFAULT_PORT = 8000
MAX_LIMIT = 500

LIST_FIELDS = (
    "id", "name", "website", "one_liner", "batch", "source", "team_size",
    "industries", "story_count", "points", "comments", "last_posted_at",
    "founder_count", "comment_count",
    # The newest scoring run. NULL until a company has been scored.
    "total", "verdict", "scored_at", "scored_by",
)
COMMENTS_PER_COMPANY = 30

_COMPANY = re.compile(r"^/api/companies/(\d+)$")


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, settings: Settings, **kwargs):
        self.settings = settings
        super().__init__(*args, **kwargs)

    # ---- routing -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - name fixed by the base class
        route = urlparse(self.path).path
        if route == "/":
            self._send(200, "text/html; charset=utf-8", INDEX_PATH.read_bytes())
        elif route == "/api/search":
            self._json(self._search(urlparse(self.path).query))
        elif match := _COMPANY.match(route):
            self._company(int(match.group(1)))
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/prepare":
            self._run(prepare, "prepare")
        elif route == "/api/score":
            self._run(score, "score")
        else:
            self._json({"error": "not found"}, status=404)

    # ---- handlers ----------------------------------------------------------

    def _search(self, query_string: str) -> dict:
        params = parse_qs(query_string)
        term = (params.get("q") or [""])[0]
        source = (params.get("source") or [None])[0] or None
        sort = (params.get("sort") or ["default"])[0]
        limit = min(int((params.get("limit") or [200])[0] or 200), MAX_LIMIT)

        report = search(
            term, settings=self.settings, limit=limit, source=source, sort=sort
        )
        return {
            "term": term,
            "total": len(report.rows),
            "companies": [{f: row[f] for f in LIST_FIELDS} for row in report.rows],
        }

    def _company(self, company_id: int) -> None:
        """Everything known about one company, in one response."""
        with connect(self.settings.db_path) as conn:
            company = companies_repo.get(conn, company_id)
            if not company:
                self._json({"error": "not found"}, status=404)
                return

            traction = stories_repo.traction(conn, company_id)
            stories = stories_repo.for_company(conn, company_id)
            people = founders_repo.for_company(conn, company_id)
            # Submitter's own words first - that is what metric 4 reads.
            thread = comments_repo.for_company(conn, company_id, COMMENTS_PER_COMPANY)
            analysis = analyses_repo.latest(conn, company_id)
            repo = repos_repo.for_company(conn, company_id)

        self._json({
            "analysis": {
                **{k: analysis[k] for k in analysis.keys() if k != "scores_json"},
                "scores": json.loads(analysis["scores_json"]),
            } if analysis else None,
            "company": {k: company[k] for k in company.keys() if k != "raw_json"},
            # `homepage` is the company's real address for the 289 whose stored
            # website is a repository URL. See 0006.
            "github": {k: repo[k] for k in repo.keys() if k != "raw_json"} if repo else None,
            "traction": dict(traction) if traction else None,
            "stories": [
                {k: row[k] for k in row.keys() if k != "raw_json"} for row in stories
            ],
            "founders": [
                {
                    **{k: row[k] for k in row.keys() if k not in ("raw_json", "prior_roles_json")},
                    "prior_roles": json.loads(row["prior_roles_json"] or "[]"),
                }
                for row in people
            ],
            "comments": [dict(row) for row in thread],
        })

    def _run(self, stage, name: str) -> None:
        """Run one stage over a selection and return its report.

        Both stages take the same body and block until done. Prepare is about
        10s for 15 companies; scoring is slower, so the UI calls them
        separately and shows the first result before the second starts.
        """
        length = int(self.headers.get("Content-Length") or 0)
        try:
            ids = json.loads(self.rfile.read(length) or b"{}").get("ids") or []
            ids = [int(i) for i in ids]
        except (ValueError, TypeError) as exc:
            self._json({"error": f"bad request: {exc}"}, status=400)
            return

        try:
            report = stage(ids, settings=self.settings)
        except TooManySelected as exc:
            self._json({"error": str(exc), "max": MAX_SELECTION}, status=400)
            return
        except ValueError as exc:
            # An empty or unknown selection is the caller's mistake, not ours.
            self._json({"error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001 - surface the reason to the UI
            log.warning("%s %s failed: %s", name, ids, exc)
            self._json({"error": str(exc)}, status=500)
            return

        # `message` is a property, so it is not in __dict__. The UI shows it
        # verbatim: the rule it describes belongs to the stage, not the page.
        self._json({**report.__dict__, "message": getattr(report, "message", "")})

    # ---- plumbing ----------------------------------------------------------

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The page is read from disk on every request, so a browser holding an
        # old copy shows behaviour the code no longer has. That has cost two
        # debugging sessions; a local viewer has nothing to gain from caching.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, "application/json", json.dumps(payload, default=str).encode())

    def log_message(self, fmt: str, *args) -> None:
        """Route access logs through logging so -v controls them."""
        log.info("%s %s", self.address_string(), fmt % args)


def serve(
    *,
    settings: Settings = default_settings,
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
) -> None:
    """Run until interrupted. Called by cli.cmd_serve."""
    handler = partial(Handler, settings=settings)
    with ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"next-billion viewer → http://{host}:{port}   (ctrl-c to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve(port=parser.parse_args().port)
