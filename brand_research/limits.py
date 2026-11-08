"""Conservative run-wide budgets. Failed requests count; retries are disabled."""

from dataclasses import asdict, dataclass


class LimitReached(RuntimeError):
    pass


class ProviderError(RuntimeError):
    """Safe error text only: never provider bodies, request URLs or API keys."""


@dataclass
class Budget:
    max_searches: int = 30
    max_ai_calls: int = 6
    max_tokens: int = 100_000
    searches: int = 0
    ai_calls: int = 0
    tokens: int = 0

    def __post_init__(self):
        if any(v < 0 for v in (self.max_searches, self.max_ai_calls, self.max_tokens)):
            raise ValueError("Budgets cannot be negative.")

    def reserve_search(self):
        if self.searches >= self.max_searches:
            raise LimitReached("SerpApi request limit reached; remaining fields may be unverified.")
        self.searches += 1

    def reserve_ai(self, token_bound: int):
        if self.ai_calls >= self.max_ai_calls:
            raise LimitReached("OpenAI request limit reached; remaining fields may be unverified.")
        if self.tokens + token_bound > self.max_tokens:
            raise LimitReached(
                "OpenAI token budget cannot cover the next request; no request sent."
            )
        self.ai_calls += 1
        self.tokens += token_bound

    def settle_tokens(self, reserved: int, actual: int | None):
        # Missing/failed usage retains the full reservation rather than claiming zero use.
        if actual is not None and actual >= 0:
            self.tokens += actual - reserved

    def snapshot(self) -> dict[str, int]:
        return asdict(self)
