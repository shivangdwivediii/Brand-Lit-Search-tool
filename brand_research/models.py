"""Small, serializable research records shared by demo, live research and Excel."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

UNVERIFIED = "Unable to verify"
NOT_ACQUIRED = "Not acquired"
FIELDS = {
    "original_company": "Original launching company",
    "founding_year": "Brand founding year",
    "origin_country": "Brand country of origin",
    "latest_acquirer": "Latest acquiring company",
    "acquisition_year": "Latest acquisition year",
}
EXTRA_COLUMNS = ["Research status", "Research mode", "Researched at (UTC)", "Research notes"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_url(value: str) -> bool:
    """Only public-looking HTTP(S) links, never executable Excel link targets."""
    import ipaddress

    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
            return False
        if any(c.isspace() or ord(c) < 32 for c in value) or len(value) > 2048:
            return False
        if host == "localhost" or host.endswith((".local", ".localhost")) or "." not in host:
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


@dataclass
class Source:
    id: str
    url: str
    title: str
    snippet: str
    query: str = ""
    tier: int = 6
    kind: str = "broader research"


@dataclass
class Evidence:
    source_id: str
    quote: str


@dataclass
class Fact:
    value: str | int | None = None
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ResearchResult:
    brand: str
    context: str
    mode: str = "Fast"
    demo: bool = False
    researched_at: str = field(default_factory=utc_now)
    facts: dict[str, Fact] = field(default_factory=lambda: {key: Fact() for key in FIELDS})
    sources: list[Source] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cache_hit: bool = False

    @property
    def status(self) -> str:
        if self.demo:
            return "DEMO — fictional fixtures"
        n = sum(f.value is not None and bool(f.evidence) for f in self.facts.values())
        return (
            "Verified" if n == len(FIELDS) else f"Partial ({n}/{len(FIELDS)})" if n else UNVERIFIED
        )

    def event(self, event: str, message: str, **details: Any) -> None:
        self.events.append(
            {"Timestamp (UTC)": utc_now(), "Event": event, "Message": message, **details}
        )
