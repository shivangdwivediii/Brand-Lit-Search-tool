# Validation report

Validated on **8 November 2026**, entirely in **Codex Cloud**, using Python **3.12.14**. No software was installed on the user's laptop. No real API key was required or used.

## Results

| Check | Result |
| --- | --- |
| Initial offline MVP, before live integration | **9 passed** |
| Final automated suite: `python -m pytest -q` | **79 passed in 2.80 seconds** |
| Ruff static checks: `ruff check .` | **Passed** |
| Ruff formatting: `ruff format --check .` | **Passed — 21 Python files formatted** |
| Dependency compatibility: `python -m pip check` | **Passed — no broken requirements** |
| Real Chromium browser smoke test | **7 checkpoints passed** |
| Application exceptions during browser test | **0** |
| Browser JavaScript exceptions during browser test | **0** |

Commands were run through the project-local `work/.venv`. Runtime packages were installed from `requirements.txt`; browser dependencies were installed separately from `requirements-browser.txt`. The app ran on port 8501 in the cloud environment.

## Excel verification

Tests generated, saved and reopened real `.xlsx` workbooks with openpyxl. They inspected both cell objects and the XLSX ZIP's external hyperlink relationships.

- Both **Brand + Parent Company** and **Brand + Category** workbooks retained their original input values and headers.
- Both context columns together, extra columns, numeric values, dates and leading-zero text were also preserved.
- Each of the ten supported fictional research cells had its own exact source hyperlink and evidence comment.
- The five unresolved fictional cells contained **Unable to verify** and had **no hyperlink**.
- The three browser-downloaded workbooks each had **10 linked research cells**, **5 unlinked unknowns**, and **28 Research Log entries**.
- Different facts linked to the appropriate distinct history/acquisition URLs. All supporting citations were present in comments and the log.
- Text resembling Excel formulas was exported literally, and actual formula inputs were rejected.
- Invalid/missing/duplicate headers, oversized inputs, excess rows/columns, blank inputs and XML entities were rejected safely.

Demo sources use reserved `.example` URLs by design; the tests verify hyperlink targets and Excel relationships, not the existence of fictional websites. The demo workbook and comments prominently disclose this.

## Live integration verification without paid requests

The real OpenAI Python SDK was exercised using an in-memory HTTP mock transport. The tests validated its Chat Completions request, strict JSON schema, output-token cap, actual-usage accounting, 429 handling, absence of hidden retries and safe error messages. SerpApi adapter tests validated the Google engine, recent-search filter, public organic snippets, LinkedIn profile exclusion, malformed/error responses and request accounting. Provider URLs, keys and raw error bodies were not exposed in user-facing errors.

Research workflow tests exercised Fast (5 searches / 1 extraction) and Deep (10 searches / 2 extractions), progress callbacks, repeated brands, source-priority ranking, retention of late ownership evidence, cache isolation/expiry, search failures and hard API/token limits. These tests use simulated responses, not authenticated external calls.

Evidence checks rejected invented sources, invented excerpts, unsupported values, low confidence, unsafe URLs, identity mismatches, invalid/future years, pending transactions, acquirer/year mismatches and incomplete ownership research. “Not acquired” was accepted only with explicit two-publisher corroboration and complete acquisition searches; silence, “privately held,” same-site subdomains and inadequate evidence were rejected. Deep conflicts and a failed/limited second extraction could retract first-pass ownership claims.

## Browser checks

`python -u -m scripts.browser_smoke` ran against the actual Streamlit server with `/usr/bin/chromium`:

1. Built-in demo research, browser download and workbook validation.
2. Evidence/activity tab opened successfully.
3. Uploaded Parent Company example, researched, downloaded and validated it.
4. Uploaded Category example, researched, downloaded and validated it.
5. Live mode with a real uploaded file and missing keys was disabled with setup guidance.
6. Mobile viewport (390 × 844) rendered successfully; desktop viewport was 1440 × 1100.
7. No browser JavaScript or Streamlit exceptions occurred.

The script stores screenshots and downloaded test files under ignored `work/browser-smoke/`. The Streamlit AppTest suite separately tested complete demo execution, cache reuse on rerun and missing-key gating. Browser testing uncovered a test synchronization race involving an old download button; using independent upload sessions resolved it. Mixed numeric/unknown year columns are converted to strings for display while their Excel export retains typed year values.

## Limits of this validation

- **No authenticated SerpApi/OpenAI research was performed.** No keys are configured, and the initial Codex network allowlist lacks `serpapi.com` and `api.openai.com`. Add those hosts and server-side secrets before a later live smoke test.
- **No deployment was performed.** Streamlit Community Cloud compatibility is prepared through `app.py`, pinned runtime requirements and server secrets instructions, but requires the user's GitHub save and deployment action.
- Only Python 3.12 was executed in this environment. Future GitHub CI is configured for Python 3.11, 3.12 and 3.13; those remote jobs have not run.
- Live results rely on public Google search excerpts and AI semantic extraction. Deterministic grounding checks cannot guarantee that an excerpt is current, complete, independently authored or semantically correct. Source review remains necessary.
- Demo/example brands and all linked demo pages are fictional. No real brand's history or ownership was verified by these offline tests.

## Review state

The repository was empty at the initial build. For the subsequent user-authorized GitHub save, the implementation is placed on `feature/brand-intelligence-platform`, based on the existing `main` commit `d6ca941afc9f8ad1390ca47d40425d971605b3c6`. Its original README introduction is preserved. The complete source, tests, fictional examples, CI workflow, placeholder secrets template and documentation are included for review. No merge or application deployment was performed. See `SECURITY_REVIEW.md` for the pre-commit data/credential review. The README contains cloud-only development and user-initiated Streamlit Community Cloud setup steps.
