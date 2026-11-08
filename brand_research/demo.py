"""Deterministic, fictional fixtures. No API calls, keys or real-world claims."""

from .models import FIELDS, NOT_ACQUIRED, Evidence, Fact, ResearchResult, Source


def demo_research(brand: str, context: str = "", mode: str = "Fast") -> ResearchResult:
    result = ResearchResult(brand, context, mode, demo=True)
    result.notes.append("FICTIONAL DEMO: reserved .example URLs demonstrate hyperlinks only.")
    name = brand.strip().casefold()
    if name == "aurora tea":
        history = Source(
            "s1",
            "https://research-demo.example/aurora-tea/history",
            "Aurora Tea history (fictional)",
            "Aurora Tea was launched by Aurora Tea Company in 1998 in India.",
            tier=1,
            kind="fictional official fixture",
        )
        deal = Source(
            "s2",
            "https://research-demo.example/northstar/aurora-acquisition",
            "Acquisition announcement (fictional)",
            "Northstar Consumer Group completed the acquisition of Aurora Tea in 2021.",
            tier=1,
            kind="fictional official fixture",
        )
        result.sources = [history, deal]
        values = ["Aurora Tea Company", 1998, "India", "Northstar Consumer Group", 2021]
        for key, value in zip(FIELDS, values, strict=True):
            source = deal if key in {"latest_acquirer", "acquisition_year"} else history
            result.facts[key] = Fact(value, [Evidence(source.id, source.snippet)])
    elif name == "harbor soap":
        history = Source(
            "s1",
            "https://research-demo.example/harbor-soap/about",
            "Harbor Soap (fictional)",
            "Harbor Works launched Harbor Soap in 2006 in the United Kingdom. Harbor Soap has never been acquired and remains independently owned.",
            tier=1,
            kind="fictional official fixture",
        )
        corroboration = Source(
            "s2",
            "https://independent-demo.example/harbor-soap/ownership",
            "Independent ownership profile (fictional)",
            "Harbor Soap remains independently owned and has never been acquired.",
            tier=3,
            kind="fictional corroborating fixture",
        )
        result.sources = [history, corroboration]
        values = ["Harbor Works", 2006, "United Kingdom", NOT_ACQUIRED, NOT_ACQUIRED]
        for key, value in zip(FIELDS, values, strict=True):
            evidence = [Evidence(history.id, history.snippet)]
            if key in {"latest_acquirer", "acquisition_year"}:
                evidence.append(Evidence(corroboration.id, corroboration.snippet))
            result.facts[key] = Fact(value, evidence)
    else:
        result.notes.append("No fixture for this brand. Try Aurora Tea or Harbor Soap.")
    result.event("demo", "Offline fixture used; zero API requests.")
    return result
