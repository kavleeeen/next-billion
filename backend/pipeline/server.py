"""A local viewer for everything the pipeline has collected.

Standard library only, no framework and no build step:

    GET  /                          the single-page UI
    GET  /api/search?q=&source=&sort=&limit=
    GET  /api/companies/{id}        detail: traction, founders, stories, comments, score
    POST /api/sync                  {topic: "..."} - collect companies for a topic
    POST /api/prepare               {ids: [...]} - threads + founders for a selection
    POST /api/score                 {ids: [...]} - five metrics and a verdict

Bound to 127.0.0.1 by default — this is a viewer, not a service. When it is
hosted, reading stays open and writing does not: POST spends PDL credits and
Gemini quota, so it needs the WRITE_TOKEN secret. See
docs/decisions/0015-hosting-the-viewer.md.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
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
from .sync import sync
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

WRITE_TOKEN_ENV = "WRITE_TOKEN"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def _write_allowed(sent: str | None, host: str) -> bool:
    """Who may spend money.

    On loopback the only caller is the person running the process, so writing
    is open. Bound to anything else the URL is reachable, and POST spends PDL
    credits and Gemini quota, so it needs the token. Unset token means the
    deployment is read-only, which is the safe default rather than an open one.
    """
    if host in LOOPBACK:
        return True
    expected = os.environ.get(WRITE_TOKEN_ENV)
    if not expected:
        return False
    # Constant time, so a wrong token cannot be guessed byte by byte.
    return hmac.compare_digest(sent or "", expected)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, settings: Settings, host: str = "127.0.0.1", **kwargs):
        self.settings = settings
        self.bind_host = host
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
        if not _write_allowed(self.headers.get("X-Write-Token"), self.bind_host):
            self._json({"error": "read-only: collecting and scoring are disabled here"},
                       status=403)
            return
        if route == "/api/sync":
            self._sync()
        elif route == "/api/prepare":
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

    def _sync(self) -> None:
        """Collect companies for a topic. Minutes, not seconds, so the page
        shows a waiting state rather than blocking on a spinner."""
        length = int(self.headers.get("Content-Length") or 0)
        try:
            topic = (json.loads(self.rfile.read(length) or b"{}").get("topic") or "").strip()
        except ValueError as exc:
            self._json({"error": f"bad request: {exc}"}, status=400)
            return

        try:
            report = sync(topic, settings=self.settings)
        except ValueError as exc:
            self._json({"error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001 - surface the reason to the UI
            log.warning("sync %r failed: %s", topic, exc)
            self._json({"error": str(exc)}, status=500)
            return

        self._json({**report.__dict__, "topic": topic,
                    "message": getattr(report, "message", "")})

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
    """Run until interrupted. Called by cli.cmd_serve.

    A host runtime states the port in $PORT, which wins over the default.
    """
    port = int(os.environ.get("PORT") or port)
    handler = partial(Handler, settings=settings, host=host)
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
    parser.add_argument("--host", default="127.0.0.1",
                        help="0.0.0.0 to accept connections from outside")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show what collecting and scoring are doing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    serve(port=args.port, host=args.host)
