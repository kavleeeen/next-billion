"""Stage 4: give a score to a prepared selection.

Runs after `prepare`, which is what puts the launch threads and the founders in
place. Scoring a company whose evidence was never gathered is not an error, but
it produces a low, uncited score, and rule 4 holds the verdict at Watch.

    build the bundle   database only, deterministic
    ask the model      one call for each company, plus a correction turn
    apply the rules    Python, never the model
    append a row       history is kept; the list reads the newest row

A company scored inside `settings.refresh_after_hours` with the same model and
prompt is left alone. Scoring costs no money on the free tier, but it costs
time and free-tier quota, and a second identical score has no value.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import Settings, settings as default_settings
from .db import connect
from .evidence import Bundle, build as build_bundle
from .prepare import MAX_SELECTION, TooManySelected
from .repository import analyses as analyses_repo
from .repository import companies as companies_repo
from .scoring import apply as apply_rules
from .scoring import gemini
from .scoring import prompt as prompt_builder

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoreReport:
    companies: int
    scored: int
    reused: int
    failed: int
    problems_remaining: int
    dropped_claims: int
    refresh_hours: float = 1.0
    results: tuple[dict, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def message(self) -> str:
        """One line a person can act on.

        The freshness rule lives in this module, so the sentence explaining it
        does too. A caller that repeated the rule would be a second copy, free
        to disagree with the first.
        """
        window = ("the last hour" if self.refresh_hours == 1
                  else f"the last {self.refresh_hours:g} hours")

        if self.scored == 0 and self.failed == 0 and self.reused:
            return (f"Nothing to score: all {self.reused} selected "
                    f"{'company was' if self.reused == 1 else 'companies were'} "
                    f"scored in {window}, so those scores are reused.")

        parts = []
        if self.scored:
            parts.append(f"{self.scored} scored")
        if self.reused:
            parts.append(f"{self.reused} reused a score from {window}")
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.dropped_claims:
            parts.append(f"{self.dropped_claims} claim(s) dropped, citation not in the evidence")
        return ". ".join(parts) + "." if parts else "Nothing to do."

    def render(self) -> str:
        lines = [
            self.message,
            "-" * 46,
            f"companies selected  : {self.companies}",
            f"scored now          : {self.scored}",
            f"reused a fresh score: {self.reused}",
            f"failed              : {self.failed}",
        ]
        if self.dropped_claims:
            lines.append(f"claims dropped      : {self.dropped_claims} (citation not in evidence)")
        if self.problems_remaining:
            lines.append(f"unresolved problems : {self.problems_remaining}")
        if self.results:
            lines.append("-" * 46)
            for row in sorted(self.results, key=lambda r: -r["total"]):
                lines.append(f"  {row['total']:>5.1f}  {row['verdict']:<14}  {row['name']}")
        for error in self.errors:
            lines.append(f"  ! {error}")
        return "\n".join(lines)


def _score_one(bundle: Bundle, settings: Settings) -> tuple[Bundle, gemini.Reply]:
    """The network half. Runs in a worker; touches no database."""
    return bundle, gemini.score(bundle, settings=settings.gemini)


def score(
    company_ids: list[int],
    *,
    settings: Settings = default_settings,
    force: bool = False,
) -> ScoreReport:
    """Score a selection. Safe to re-run: a fresh score is reused, not repeated."""
    if not company_ids:
        raise ValueError("no companies selected")
    if len(company_ids) > MAX_SELECTION:
        raise TooManySelected(
            f"{len(company_ids)} companies selected; the limit is {MAX_SELECTION}"
        )

    if not settings.gemini.token:
        raise gemini.MissingToken(
            f"{settings.gemini.token_env} is not set. Put it in .env at the repo root."
        )


    with connect(settings.db_path) as conn:
        known = [row["id"] for row in companies_repo.by_ids(conn, company_ids)]
        missing = set(company_ids) - set(known)
        if missing:
            log.warning("no such company: %s", sorted(missing))
        if not known:
            raise ValueError("none of the selected ids exist")

        fresh = set() if force else analyses_repo.fresh_company_ids(
            conn, known,
            model=settings.gemini.model,
            prompt_version=prompt_builder.VERSION,
            within_hours=settings.refresh_after_hours,
        )
        pending = [company_id for company_id in known if company_id not in fresh]

        # Bundles are built before any call, so every database read happens on
        # this thread and the workers only do network.
        bundles = [build_bundle(conn, company_id) for company_id in pending]

    replies: list[tuple[Bundle, gemini.Reply]] = []
    errors: list[str] = []

    if bundles:
        with ThreadPoolExecutor(max_workers=settings.gemini.workers) as pool:
            futures = [pool.submit(_score_one, bundle, settings) for bundle in bundles]
            for bundle, future in zip(bundles, futures):
                try:
                    replies.append(future.result())
                except Exception as exc:  # noqa: BLE001 - one company must not stop the batch
                    log.warning("scoring %s failed: %s", bundle.name, exc)
                    errors.append(f"{bundle.name}: {exc}")

    results: list[dict] = []
    problems = dropped = 0

    with connect(settings.db_path) as conn:
        for bundle, reply in replies:
            analysis = apply_rules.apply(
                reply.payload, bundle,
                model=reply.model, prompt_version=reply.prompt_version,
            )
            analyses_repo.insert(
                conn,
                company_id=analysis.company_id,
                verdict=analysis.verdict,
                total=analysis.total,
                scores=analysis.to_json(),
                model=analysis.model,
                prompt_version=analysis.prompt_version,
            )
            conn.commit()   # keep each score, whatever happens to the next one

            problems += len(reply.problems)
            dropped += len(analysis.dropped_claims)
            results.append({
                "id": analysis.company_id,
                "name": analysis.name,
                "total": analysis.total,
                "verdict": analysis.verdict,
            })

        # The reused ones still belong in the reply, so the list can show them.
        for company_id in known:
            if company_id in fresh:
                row = analyses_repo.latest(conn, company_id)
                if row:
                    results.append({
                        "id": company_id,
                        "name": companies_repo.get(conn, company_id)["name"],
                        "total": row["total"],
                        "verdict": row["verdict"],
                        "reused": True,
                    })

    return ScoreReport(
        companies=len(known),
        scored=len(replies),
        reused=len(fresh),
        failed=len(errors),
        problems_remaining=problems,
        dropped_claims=dropped,
        refresh_hours=settings.refresh_after_hours,
        results=tuple(results),
        errors=tuple(errors),
    )
