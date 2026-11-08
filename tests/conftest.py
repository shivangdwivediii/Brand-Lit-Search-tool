import copy

import pytest

from brand_research.demo import demo_research


@pytest.fixture
def live_case():
    result = demo_research("Aurora Tea", "Parent Company: Northstar Consumer Group")
    result.demo = False
    result.notes.clear()
    result.events.clear()
    payload = {
        "identity_matched": True,
        "facts": {
            key: {
                "value": fact.value,
                "confidence": "high",
                "evidence": [{"source_id": e.source_id, "quote": e.quote} for e in fact.evidence],
            }
            for key, fact in result.facts.items()
        },
        "acquisition": {
            "status": "acquired",
            "latest_checked": True,
            "completed": True,
            "conflict": False,
        },
        "notes": [],
    }
    from brand_research.models import FIELDS, Fact

    result.facts = {key: Fact() for key in FIELDS}
    return result, copy.deepcopy(payload)
