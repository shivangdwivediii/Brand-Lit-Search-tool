"""Reject ungrounded, mismatched, unsafe and incomplete per-cell citations."""

import re
from datetime import UTC, datetime

from .models import FIELDS, NOT_ACQUIRED, Evidence, Fact, ResearchResult, safe_url
from .providers import host_of


def squash(text: str) -> str:
    return " ".join(text.casefold().split())


def value_in_quote(value: str | int, quote: str) -> bool:
    # Word boundaries prevent 'US' matching 'industry' or '1998' matching '19980'.
    return bool(re.search(r"(?<!\w)" + re.escape(squash(str(value))) + r"(?!\w)", squash(quote)))


def validate_extraction(payload: dict, result: ResearchResult, ownership_complete: bool) -> None:
    if payload.get("identity_matched") is not True:
        result.notes.append("Brand identity could not be matched to the supplied context.")
        return
    sources = {s.id: s for s in result.sources}
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        result.notes.append("Invalid extraction structure; no facts accepted.")
        return
    acquisition = payload.get("acquisition", {})
    if not isinstance(acquisition, dict):
        acquisition = {}
    for key in FIELDS:
        raw = facts.get(key)
        if not isinstance(raw, dict) or raw.get("confidence") != "high":
            continue
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        if isinstance(value, str):
            value = value.strip()
            if (
                not value
                or len(value) > 250
                or value.casefold() in {"unknown", "n/a", "none", "unable to verify", "not known"}
            ):
                continue
        if key in {"founding_year", "acquisition_year"} and value != NOT_ACQUIRED:
            if not isinstance(value, int) or not 1000 <= value <= datetime.now(UTC).year:
                continue
        elif key not in {"founding_year", "acquisition_year"} and not isinstance(value, str):
            continue
        if value == NOT_ACQUIRED and key not in {"latest_acquirer", "acquisition_year"}:
            continue
        evidence = []
        raw_evidence = raw.get("evidence", [])
        if not isinstance(raw_evidence, list):
            continue
        for item in raw_evidence[:5]:
            if not isinstance(item, dict):
                continue
            source_id, quote = item.get("source_id"), item.get("quote")
            if not isinstance(source_id, str) or not isinstance(quote, str):
                continue
            source = sources.get(source_id)
            if not source or not safe_url(source.url) or len(quote.strip()) < 15:
                continue
            if squash(quote) not in squash(source.snippet):
                continue
            if value != NOT_ACQUIRED and not value_in_quote(value, quote):
                continue
            evidence.append(Evidence(source_id, quote.strip()))
        if evidence:
            result.facts[key] = Fact(value, evidence)
        else:
            result.event("rejected", "Citation/quote/value validation failed.", Field=FIELDS[key])

    acquisition_keys = ("latest_acquirer", "acquisition_year")
    negative = any(result.facts[k].value == NOT_ACQUIRED for k in acquisition_keys)
    if negative:
        # Require both cells to cite explicit negative evidence from two publishers, including
        # a primary-domain candidate or a preferred business profile. No-result inference fails.
        def sufficient(fact: Fact) -> bool:
            hosts = set()
            preferred = False
            for evidence in fact.evidence:
                source = sources[evidence.source_id]
                text = squash(evidence.quote)
                explicit = any(
                    p in text
                    for p in (
                        "never been acquired",
                        "never acquired",
                        "has not been acquired",
                        "remains independently owned since",
                        "independently owned since its founding",
                    )
                )
                if explicit:
                    hosts.add(host_of(source.url))
                    preferred |= source.tier <= 2
            # Hostnames on the same registered publisher are not independent corroboration.
            publishers = {
                ".".join(h.split(".")[-3:])
                if h.endswith((".co.uk", ".com.au", ".co.in"))
                else ".".join(h.split(".")[-2:])
                for h in hosts
            }
            return len(publishers) >= 2 and preferred

        valid = (
            ownership_complete
            and acquisition.get("status") == "not_acquired"
            and acquisition.get("latest_checked") is True
            and acquisition.get("conflict") is False
            and all(
                result.facts[k].value == NOT_ACQUIRED and sufficient(result.facts[k])
                for k in acquisition_keys
            )
        )
        if not valid:
            for key in acquisition_keys:
                result.facts[key] = Fact()
            result.notes.append(
                "Not acquired rejected: explicit independent corroboration or complete ownership research was missing."
            )
    else:
        valid = (
            ownership_complete
            and acquisition.get("status") == "acquired"
            and acquisition.get("latest_checked") is True
            and acquisition.get("completed") is True
            and acquisition.get("conflict") is False
        )
        if not valid:
            for key in acquisition_keys:
                result.facts[key] = Fact()
            if any(
                isinstance(facts.get(k), dict) and facts[k].get("value") is not None
                for k in acquisition_keys
            ):
                result.notes.append(
                    "Latest completed acquisition could not be established; acquisition fields withheld."
                )
        else:
            # Pending deals cannot become completed acquisitions through a model flag alone.
            for key in acquisition_keys:
                fact = result.facts[key]
                fact.evidence = [
                    e
                    for e in fact.evidence
                    if re.search(
                        r"acquired|purchased|bought|completed|closed|merged", e.quote, re.I
                    )
                    and not re.search(
                        r"will (?:be )?acquir|agreed to (?:be )?acquir|plans? to|proposed|pending|expected to|subject to",
                        e.quote,
                        re.I,
                    )
                ]
                if not fact.evidence:
                    result.facts[key] = Fact()
            company = result.facts["latest_acquirer"]
            year = result.facts["acquisition_year"]
            if company.value is not None and year.value is not None:
                same_deal = any(
                    value_in_quote(company.value, e.quote) and value_in_quote(year.value, e.quote)
                    for e in company.evidence + year.evidence
                )
                if not same_deal:
                    for key in acquisition_keys:
                        result.facts[key] = Fact()
                    result.notes.append(
                        "Acquirer and year could not be tied to the same completed transaction."
                    )
    founding, acquired = result.facts["founding_year"], result.facts["acquisition_year"]
    if (
        isinstance(founding.value, int)
        and isinstance(acquired.value, int)
        and acquired.value < founding.value
    ):
        for key in acquisition_keys:
            result.facts[key] = Fact()
        result.notes.append(
            "Acquisition predates brand founding; conflicting acquisition values withheld."
        )
    notes = payload.get("notes", [])
    if isinstance(notes, list):
        result.notes.extend(str(n)[:1000] for n in notes[:10])
