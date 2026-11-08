import copy

import pandas as pd
import pytest

from brand_research.engine import CACHE_TTL, ResearchEngine, SessionCache, select_sources
from brand_research.limits import Budget, ProviderError
from brand_research.models import Source


class Search:
    def __init__(self, budget, sources, fail_at=None):
        self.budget, self.sources, self.fail_at = budget, sources, fail_at
        self.calls = []

    def search(self, query, brand, context, recent=False):
        self.budget.reserve_search()
        self.calls.append((query, recent))
        if self.fail_at == len(self.calls):
            raise ProviderError("Simulated search failure")
        return copy.deepcopy(self.sources)


class Extractor:
    def __init__(self, budget, payload, second=None):
        self.budget, self.payload, self.second = budget, payload, second

    def extract(self, brand, context, sources, as_of):
        self.budget.reserve_ai(100)
        payload = self.second if self.budget.ai_calls > 1 and self.second else self.payload
        return copy.deepcopy(payload)


def engine_for(live_case, budget=None, fail_at=None, second=None):
    result, payload = live_case
    budget = budget or Budget()
    search = Search(budget, result.sources, fail_at)
    engine = ResearchEngine(search, Extractor(budget, payload, second), budget)
    return engine, search


@pytest.mark.parametrize("mode,searches,ai", [("Fast", 5, 1), ("Deep", 10, 2)])
def test_modes_limits_progress_and_cache(live_case, mode, searches, ai):
    engine, search = engine_for(live_case)
    progress = []
    result = engine.research(
        "Aurora Tea", "Parent Company: Northstar Consumer Group", mode, progress=progress.append
    )
    assert result.status == "Verified"
    assert engine.budget.searches == searches
    assert engine.budget.ai_calls == ai
    assert progress
    if mode == "Deep":
        assert any(recent for _, recent in search.calls)
        assert any('"Northstar Consumer Group"' in query for query, _ in search.calls)
    cached = engine.research("Aurora Tea", "Parent Company: Northstar Consumer Group", mode)
    assert cached.cache_hit
    assert cached.researched_at == result.researched_at
    assert engine.budget.searches == searches
    cached.facts["original_company"].value = "Mutated"
    assert (
        engine.research("Aurora Tea", "Parent Company: Northstar Consumer Group", mode)
        .facts["original_company"]
        .value
        != "Mutated"
    )


def test_api_failure_does_not_imply_no_acquisition_or_poison_cache(live_case):
    engine, _ = engine_for(live_case, fail_at=3)
    result = engine.research("Aurora Tea")
    assert result.facts["latest_acquirer"].value is None
    assert result.facts["acquisition_year"].value is None
    assert result.facts["original_company"].value == "Aurora Tea Company"
    assert not engine.cache.entries
    assert any(event["Event"] == "error" for event in result.events)


def test_budget_exhaustion_retains_all_rows_and_original_data(live_case):
    engine, _ = engine_for(live_case, Budget(max_searches=2))
    frame = pd.DataFrame(
        {
            "Brand": ["Aurora Tea", "Second Brand", None],
            "Category": ["Tea", "Tea", "Tea"],
            "Keep": ["001", "002", "003"],
        }
    )
    before = frame.copy(deep=True)
    results = engine.run(frame, "Fast", demo=False)
    pd.testing.assert_frame_equal(frame, before)
    assert len(results) == 3
    assert engine.budget.searches == 2
    assert results[0].facts["latest_acquirer"].value is None
    assert results[1].status == "Unable to verify"
    assert "Blank brand" in results[2].notes[0]


def test_deep_second_pass_can_retract_conflicting_first_pass(live_case):
    _, payload = live_case
    second = copy.deepcopy(payload)
    second["acquisition"]["conflict"] = True
    engine, _ = engine_for(live_case, second=second)
    result = engine.research("Aurora Tea", mode="Deep")
    assert result.facts["latest_acquirer"].value is None


def test_deep_search_failure_withholds_first_pass_ownership(live_case):
    engine, _ = engine_for(live_case, fail_at=8)
    result = engine.research("Aurora Tea", mode="Deep")
    assert result.facts["latest_acquirer"].value is None


def test_deep_extraction_cap_withholds_first_pass_ownership(live_case):
    engine, _ = engine_for(live_case, Budget(max_ai_calls=1))
    result = engine.research("Aurora Tea", mode="Deep")
    assert result.facts["latest_acquirer"].value is None
    assert result.facts["acquisition_year"].value is None
    assert result.facts["original_company"].value == "Aurora Tea Company"


def test_no_sources_skips_ai_and_does_not_claim_not_acquired(live_case):
    engine, search = engine_for(live_case)
    search.sources = []
    result = engine.research("Unknown")
    assert result.status == "Unable to verify"
    assert engine.budget.ai_calls == 0


def test_cache_isolation_ttl_and_clear():
    from brand_research.demo import demo_research

    clock = [0]
    cache = SessionCache(clock=lambda: clock[0])
    key = cache.key("Brand", "Category: Tea", "Fast", False, "model")
    cache.put(key, demo_research("Brand"))
    assert cache.get(key)
    for changed in [
        ("Other", "Category: Tea", "Fast", False, "model"),
        ("Brand", "Category: Soap", "Fast", False, "model"),
        ("Brand", "Category: Tea", "Deep", False, "model"),
        ("Brand", "Category: Tea", "Fast", True, "model"),
        ("Brand", "Category: Tea", "Fast", False, "other-model"),
    ]:
        assert cache.get(cache.key(*changed)) is None
    assert SessionCache().get(key) is None
    clock[0] = CACHE_TTL
    assert cache.get(key) is None
    cache.put(key, demo_research("Brand"))
    cache.clear()
    assert not cache.entries


def test_duplicates_reuse_cache_without_dropping_rows():
    frame = pd.DataFrame({"Brand": ["Aurora Tea", "Aurora Tea"], "Category": ["Tea", "Tea"]})
    results = ResearchEngine().run(frame, "Fast", demo=True)
    assert len(results) == 2
    assert not results[0].cache_hit
    assert results[1].cache_hit


def test_late_low_priority_ownership_evidence_is_kept():
    sources = [
        Source(f"s{i}", f"https://preferred.example/{i}", "", "", query=f"q{i // 10}", tier=2)
        for i in range(50)
    ]
    sources.append(
        Source(
            "latest",
            "https://press.example/latest",
            "",
            "A recent deal",
            query="latest ownership",
            tier=7,
        )
    )
    selected = select_sources(sources)
    assert len(selected) == 30
    assert any(s.id == "latest" for s in selected)
