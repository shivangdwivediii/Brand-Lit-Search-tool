"""Bounded research workflow, progress events and private session cache."""

import copy
import hashlib
import json
import re
import time
from collections.abc import Callable

import pandas as pd

from .demo import demo_research
from .excel import validate_frame
from .limits import Budget, LimitReached, ProviderError
from .models import FIELDS, Fact, ResearchResult, Source
from .providers import MAX_SOURCES, host_of
from .validation import validate_extraction

CACHE_TTL = 6 * 60 * 60
CACHE_MAX_ENTRIES = 200
PIPELINE_VERSION = "1"


class SessionCache:
    """Memory only; create one instance in each Streamlit session_state."""

    def __init__(self, clock=time.monotonic):
        self.entries = {}
        self.clock = clock

    @staticmethod
    def key(brand: str, context: str, mode: str, demo: bool, model: str) -> str:
        return hashlib.sha256(
            json.dumps(
                [
                    PIPELINE_VERSION,
                    brand.strip().casefold(),
                    context.strip().casefold(),
                    mode,
                    demo,
                    model,
                ]
            ).encode()
        ).hexdigest()

    def get(self, key: str) -> ResearchResult | None:
        item = self.entries.get(key)
        if not item:
            return None
        saved, value = item
        if self.clock() - saved >= CACHE_TTL:
            del self.entries[key]
            return None
        result = copy.deepcopy(value)
        result.cache_hit = True
        return result

    def put(self, key: str, value: ResearchResult):
        if len(self.entries) >= CACHE_MAX_ENTRIES:
            del self.entries[next(iter(self.entries))]
        self.entries[key] = (self.clock(), copy.deepcopy(value))

    def clear(self):
        self.entries.clear()


def select_sources(sources: list[Source]) -> list[Source]:
    # Keep evidence from every query, including late ownership checks, before filling
    # remaining slots in source-priority order. A profile-heavy query cannot crowd out
    # all recent transaction evidence.
    ranked = sorted(sources, key=lambda s: s.tier)
    chosen = {}
    counts = {}
    for source in ranked:
        if counts.get(source.query, 0) < 2:
            chosen[source.id] = source
            counts[source.query] = counts.get(source.query, 0) + 1
    for source in ranked:
        if len(chosen) >= MAX_SOURCES:
            break
        chosen[source.id] = source
    return sorted(list(chosen.values())[:MAX_SOURCES], key=lambda s: s.tier)


def initial_queries(brand: str, context: str = "") -> list[tuple[str, bool, bool]]:
    b = json.dumps(brand, ensure_ascii=False)
    hint = re.sub(r"Parent Company:|Category:", "", context).replace("|", " ").strip()
    preferred = "(site:linkedin.com/company OR site:bloomberg.com OR site:crunchbase.com)"
    # Tuple: query, ownership coverage, recent-only filter.
    return [
        (
            f'{b} {hint} official (history OR founded OR launched OR origin OR "our story")',
            False,
            False,
        ),
        (f"{b} (founded OR launched OR origin) {preferred}", False, False),
        (
            f'{b} (acquired OR acquisition OR takeover OR ownership OR "never acquired")',
            True,
            False,
        ),
        (f"{b} (acquired OR acquisition OR ownership) {preferred}", True, False),
        (
            f"{b} (founded OR acquired OR ownership) (site:tracxn.com OR site:pitchbook.com OR site:sec.gov OR site:reuters.com OR site:wikipedia.org)",
            True,
            False,
        ),
    ]


class ResearchEngine:
    def __init__(
        self,
        search=None,
        extractor=None,
        budget: Budget | None = None,
        cache: SessionCache | None = None,
        model: str = "gpt-4o-mini",
    ):
        self.search = search
        self.extractor = extractor
        self.budget = budget if budget is not None else Budget()
        self.cache = cache if cache is not None else SessionCache()
        self.model = model

    def research(
        self,
        brand: str,
        context: str = "",
        mode: str = "Fast",
        demo: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> ResearchResult:
        if mode not in {"Fast", "Deep"}:
            raise ValueError("Choose Fast or Deep research mode.")
        notify = progress or (lambda message: None)
        key = self.cache.key(brand, context, mode, demo, self.model)
        cached = self.cache.get(key)
        if cached:
            notify(f"{brand}: cached evidence reused")
            cached.brand, cached.context = brand, context
            return cached
        if demo:
            result = demo_research(brand, context, mode)
            self.cache.put(key, result)
            return result
        result = ResearchResult(brand, context, mode)
        if not brand.strip():
            result.notes.append("Blank brand: input row retained; no API requests made.")
            return result
        if not self.search or not self.extractor:
            raise ValueError("Live research needs both providers.")
        all_sources: dict[str, Source] = {}
        ownership_ok = True
        had_error = False

        def gather(queries):
            nonlocal ownership_ok, had_error
            for query, ownership, recent in queries:
                notify(f"{brand}: searching public evidence ({self.budget.searches + 1})")
                try:
                    sources = self.search.search(query, brand, context, recent=recent)
                    result.event("search", f"{len(sources)} public excerpts returned.", Query=query)
                    for source in sources:
                        existing = all_sources.get(source.url)
                        if not existing:
                            source.id = f"s{len(all_sources) + 1}"
                            all_sources[source.url] = source
                        elif (
                            source.snippet not in existing.snippet
                            and len(existing.snippet) + len(source.snippet) < 3600
                        ):
                            existing.snippet += "\n" + source.snippet
                    result.sources = select_sources(list(all_sources.values()))
                except (LimitReached, ProviderError) as exc:
                    had_error = True
                    if ownership:
                        ownership_ok = False
                    result.notes.append(str(exc))
                    result.event("error", str(exc), Query=query)
                    if isinstance(exc, LimitReached):
                        # Remaining ownership queries cannot run.
                        ownership_ok = False
                        break

        def extract():
            nonlocal had_error
            if not result.sources:
                result.notes.append("No usable public evidence excerpts were returned.")
                return False
            notify(f"{brand}: extracting and checking individual citations")
            try:
                payload = self.extractor.extract(
                    brand, context, result.sources, result.researched_at
                )
                # Replace rather than accumulate facts so a deeper conflicting finding can retract one.
                result.facts = {k: Fact() for k in FIELDS}
                validate_extraction(payload, result, ownership_complete=ownership_ok)
                result.event(
                    "extraction",
                    "AI response checked for identity, evidence quotes, values and ownership coverage.",
                )
                return True
            except (LimitReached, ProviderError) as exc:
                had_error = True
                result.notes.append(str(exc))
                result.event("error", str(exc))
                return False

        gather(initial_queries(brand, context))
        extract()
        if mode == "Deep":
            b = json.dumps(brand, ensure_ascii=False)
            domains = [host_of(s.url) for s in result.sources if s.tier == 1][:3]
            official_filter = (
                "(" + " OR ".join(f"site:{d}" for d in dict.fromkeys(domains)) + ")"
                if domains
                else "official company brand"
            )
            acquirer = result.facts["latest_acquirer"].value
            owner = (
                json.dumps(str(acquirer), ensure_ascii=False)
                if acquirer and acquirer != "Not acquired"
                else b
            )
            gather(
                [
                    (f"{b} (launched OR founded OR origin) {official_filter}", False, False),
                    (
                        f"{b} (acquisition OR ownership OR independent) {official_filter}",
                        True,
                        False,
                    ),
                    (f"{b} (acquired OR takeover OR divestment OR ownership) latest", True, True),
                    (
                        f"{owner} (acquired OR takeover OR sold OR ownership) latest completed",
                        True,
                        False,
                    ),
                    (
                        f"{b} (acquisition OR ownership OR founding) (site:sec.gov OR site:gov.uk OR site:reuters.com OR site:ft.com OR site:apnews.com)",
                        True,
                        False,
                    ),
                ]
            )
            if had_error:
                # An incomplete deep pass cannot certify the latest ownership from the fast pass.
                ownership_ok = False
            extraction_complete = extract()
            if not ownership_ok or not extraction_complete:
                result.facts["latest_acquirer"] = Fact()
                result.facts["acquisition_year"] = Fact()
        result.event("usage", json.dumps(self.budget.snapshot(), sort_keys=True))
        # Do not pin transient provider/quota/limit failures in cache.
        if not had_error:
            self.cache.put(key, result)
        return result

    def run(
        self, frame: pd.DataFrame, mode: str, demo: bool, progress=None
    ) -> list[ResearchResult]:
        brand_col, context_cols = validate_frame(frame)
        results = []
        for position, (_, row) in enumerate(frame.iterrows()):
            brand = "" if pd.isna(row[brand_col]) else str(row[brand_col]).strip()
            context = " | ".join(
                f"{col.strip()}: {row[col]}"
                for col in context_cols
                if pd.notna(row[col]) and str(row[col]).strip()
            )
            callback = (
                (lambda message, p=position: progress(p, len(frame), message)) if progress else None
            )
            results.append(self.research(brand, context, mode, demo, callback))
            if progress:
                progress(
                    position + 1, len(frame), f"Completed {position + 1} of {len(frame)} brands"
                )
        return results
