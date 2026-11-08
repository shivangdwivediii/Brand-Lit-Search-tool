# Brand-Lit-Search-tool

An AI-powered brand research platform.

Features:
- Upload Excel files containing Brand and Parent Company or Category.
- Research brand launch company, founding year and country of origin.
- Find latest acquisitions and acquisition years.
- Generate Excel output with source hyperlinks.


---

# BrandLit — AI Brand Research Platform

A Python + Streamlit application that enriches brand spreadsheets with evidence-backed brand history and ownership research. It runs entirely in Codex Cloud and is ready for a user-initiated Streamlit Community Cloud deployment. Nothing needs to be installed on a corporate laptop.

**Default: offline demo, no API keys required.** The demo uses fictional brands and reserved `.example` links. Its workbooks explicitly identify the results as fictional fixtures. Live mode uses Google search through SerpApi and structured extraction through OpenAI.

## What it does

- Accepts `.xlsx` input containing **Brand + Parent Company** or **Brand + Category**, including both context columns if present.
- Preserves every original input column, its header, values and row order; appends research columns.
- Researches the **original launching company**, **brand founding year**, **country of origin**, **latest acquiring company** and **latest acquisition year**.
- Links each supported researched Excel cell directly to the exact evidence URL for that value. Different cells can have different links. Comments contain supporting quotes; multiple citations are all recorded in the Research Log.
- Uses **Unable to verify** for unsupported, ambiguous or conflicting facts and interrupted research. An API error or empty search never implies **Not acquired**.
- Provides Fast/Deep modes, progress, private session caching, explicit request/token caps, examples, a complete Research Log and automated tests.

## Use it without keys

The following commands run **inside the Codex Cloud terminal**, not on your laptop. In the prepared workspace, the virtual environment is already under `work/.venv`:

```bash
cd /workspace/Brand-Lit-Search-tool
work/.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

Open port 8501 using Codex's app preview. Leave **Demo · no API keys** selected, use the fictional example, press **Start research**, and download the workbook. You can also download either example input, or upload your own workbook. Unknown demo brands return **Unable to verify**.

For a fresh cloud checkout:

```bash
python -m venv work/.venv
work/.venv/bin/python -m pip install -r requirements-dev.txt
work/.venv/bin/streamlit run app.py --server.headless true --server.address 0.0.0.0 --server.port 8501
```

The example input files are `examples/brand_parent_company.xlsx` and `examples/brand_category.xlsx`. Regenerate them with `work/.venv/bin/python -m scripts.create_examples`.

## Input rules

The **first worksheet** is used. The first row must contain unique text headers. Header matching ignores case and outer whitespace, while exported headers retain the originals. Both `Parent Company` and `Category` may be present; both are used to disambiguate the brand. Extra columns are retained and are not sent to the APIs.

| Brand | Parent Company |
| --- | --- |
| Aurora Tea | Northstar Consumer Group |
| Harbor Soap | Harbor Works |
| Mystery Brand | Unknown |

These are fictional examples, not real businesses. Category examples use Tea, Personal care and Unknown respectively.

Limits: 200 data rows, 50 columns, 10 MB uploaded size and 50 MB expanded workbook size. Brand/context fields are limited to 300 characters. Formula cells, encrypted files, duplicate or missing headers, and previously enriched output headers are rejected with an actionable message. Paste formula **values** into a new workbook before uploading. Blank worksheet rows are ignored; a nonempty row with a blank brand is retained and not researched. Formatting and source-workbook formulas are not preserved; the original **data values** are. Duplicate input rows remain separate, with cached research reused when context matches.

## Enable live research

Set server environment variables, or add these top-level keys to **Streamlit Community Cloud → App settings → Secrets**:

```toml
SERPAPI_API_KEY = "your-serpapi-key"
OPENAI_API_KEY = "your-openai-key"
OPENAI_MODEL = "gpt-4o-mini"
```

The default model must support Chat Completions with strict JSON-schema output and `max_completion_tokens`. `OPENAI_MODEL` can select another compatible model available to your OpenAI project. Environment variables override Streamlit secrets. The sidebar reports only whether each credential is configured; no credential input or secret value is displayed. `Settings` also excludes keys from its representation.

Never commit actual keys. `.streamlit/secrets.toml`, `.env*`, temporary workbooks and `work/` are ignored. `.streamlit/secrets.toml.example` contains placeholders only. The app does **not** load `.env` files automatically.

This Codex environment initially has **no API keys configured** and its network allowlist does **not** include `serpapi.com` or `api.openai.com`. To run an authenticated smoke test in Codex later, add those two exact hosts and server-side secrets in environment settings. Do not paste keys into chat or GitHub. Streamlit Community Cloud uses its own network and secret settings.

Choose **Live research**, upload real brands, select Fast or Deep, review the caps and start. Fictional built-in examples cannot be submitted in live mode. The UI does not treat a configured key as proof of service access; provider failures appear in notes and the log.

## How research and verification work

### Source order and access

1. Official brand/company domain candidates.
2. Public LinkedIn company pages and public article excerpts, Bloomberg and Crunchbase.
3. Tracxn and PitchBook.
4. Corporate filings, including SEC and company registries.
5. Reputable press and public corporate press releases.
6. Wikipedia.
7. Wider research when stronger evidence is unavailable.

Searches target preferred sources, then retain a diverse selection of up to 30 excerpts, with space reserved for each query's evidence. Domain ranking is a **heuristic**, not certification of an official site. OpenAI must independently match the brand and context. Some official parent domains cannot be recognized by spelling alone, so extraction also evaluates source identity.

**Only public organic Google snippets returned by SerpApi are processed. The app never fetches source pages.** It does not scrape LinkedIn profiles, use source-site credentials, bypass a login/paywall/robots policy, or process protected page text. A Bloomberg or PitchBook link may require a subscription when the user opens it; the workbook still cites the exact indexed page and records the excerpt actually used. Snippets may be truncated, stale, misleading or insufficient. Full-page research is a future extension, not a capability claimed by this version.

### Field definitions

- **Original launching company:** the business that first launched the brand, distinct from a founder's personal name or current parent. Missing company evidence stays unknown.
- **Brand founding year:** launch/founding of the brand itself, not the parent's incorporation year.
- **Country of origin:** origin of the brand, not current headquarters, factory location or the acquiring company's home country.
- **Latest acquisition:** latest completed controlling acquisition found for the brand or its controlling owner as of the research timestamp. Excludes minority investment, licensing, distribution, a pending deal and a mere name change. This is an automated search finding, not an exhaustive ownership audit.

The AI returns a source ID and verbatim excerpt for each proposed value. Deterministic checks require matched identity, high confidence, a known HTTP(S) source, a quoted substring of the returned snippet, and literal value support. Years must be integers between 1000 and the current year. Acquisition values require completed ownership searches, no model-reported conflict and explicit transaction evidence. Pending-deal language is rejected; the acquirer and year must be tied to the same transaction when both are known. An acquisition year predating founding is rejected. Unsupported cells export as **Unable to verify** without a hyperlink.

“Verified” in this MVP means **automatically checked against cited search excerpts**. The AI still assesses semantic entailment, company identity and transaction relevance. These checks reduce hallucinations but do not replace a human reading the source. Country names and company names keep the wording in the evidence rather than silently expanding acronyms.

### Not acquired

Both acquisition fields show **Not acquired** only when:

- Ownership/acquisition queries completed without an ownership-search error or cap interruption.
- The AI explicitly reports no acquisition, checked latest ownership and no conflict.
- Each field cites explicit never-acquired or continuing-independent-since-founding evidence from **at least two independent publisher domains**, including a preferred source.

“Privately held,” an unqualified “independent,” missing results, or a single source is insufficient. The publisher-domain check groups common domain suffixes and same-site subdomains; the AI must also assess whether sources are independently authored. Syndicated copies can still require human review. The strict rule intentionally returns unknown when research cannot prove a negative.

### Modes, limits and caching

| Mode | Maximum searches per uncached brand | Maximum AI calls | Additional work |
| --- | ---: | ---: | --- |
| Fast | 5 | 1 | History, preferred profiles, ownership and broader corroboration |
| Deep | 10 | 2 | Official-domain queries, a recent-year ownership search, controlling-owner search, filings/press and a second extraction |

Deep's second pass can retract earlier claims when new evidence conflicts. If deeper ownership research fails, earlier ownership claims are withheld. History facts may survive a failed ownership search. Failed requests and limits are logged; remaining rows are retained.

Default **per-run** caps are 30 SerpApi requests, 6 OpenAI calls and 100,000 tokens. The sidebar allows lower or higher caps within hard UI ceilings. Failed attempts count. Retries are disabled in both clients. SerpApi has a 5-second connection/35-second read timeout; OpenAI has a 45-second timeout.

Before an OpenAI call, a conservative reservation uses the UTF-8 byte length of the prompt, evidence and schema, plus 2,048 envelope tokens and a 3,000 output-token cap. If it cannot fit in the remaining token budget, the request is blocked before sending. Successful calls replace the reservation with provider-reported actual usage. Failed calls or missing usage retain the reservation. This can block calls that would in practice fit; it favors a bounded run. These counters are not currency estimates. Also set project/account billing caps with both providers: a new run/session resets application limits, and concurrent users have separate limits.

Each browser session has its **own in-memory cache**, capped at 200 entries with a six-hour expiry. Brand, full context, mode, demo/live state, model and pipeline version form the cache key. Original evidence timestamps remain unchanged on cache hits, and hits use no API calls. Transient provider/quota/limit failures are not cached. Successful unresolved searches can be cached; use **Clear session cache** to force research. There is no shared global cache or persistent database.

### Privacy

Live mode sends brand and Parent Company/Category context to SerpApi and OpenAI; no other input columns are sent. Inputs, results, downloads and caches remain in Streamlit session memory. The app does not write uploads or research data to disk. Provider policies and hosting/session lifecycle still apply; this is not an application-level authentication or organization-wide data retention system. Restrict access in Streamlit settings before using shared paid credentials for corporate data.

## Export workbook

| Worksheet | Contents |
| --- | --- |
| Brand Research | Original columns + five researched fields + status, mode, UTC timestamp and notes |
| Research Log | Input-row identity, field-level evidence, every selected source excerpt, exact URLs, queries, source tiers, validation events, errors, cache provenance and usage |
| Read Me | Data-mode disclosure, field/verification limitations, acquisition policy, access behavior and run usage |

Each supported cell contains a genuine openpyxl **external hyperlink relationship**, not an `HYPERLINK()` formula. Its comment includes all citations for that cell. Research Log URL cells are clickable too. All text, including user input, model output and snippets beginning with `=`, is written as literal strings to avoid executing Excel formulas. Unknowns do not receive citations. The workbook opens normally in Excel; corporate policies may warn before opening external links.

## Tests and cloud validation

Run from the repository root in Codex Cloud:

```bash
work/.venv/bin/python -m pytest -q
work/.venv/bin/ruff check .
work/.venv/bin/ruff format --check .
work/.venv/bin/python -m pip check
```

Tests cover both input formats, original-value preservation, real XLSX hyperlink relationships, per-cell evidence, no links on unknown cells, literal formula safety, invalid workbooks, citation rejection, acquisition uncertainty, request and token caps, safe provider errors, the actual OpenAI SDK with mock HTTP transport, Fast/Deep execution, cache isolation/expiry, progress, failures and Streamlit UI execution. All run without real API keys. The MVP's first 9 Excel/demo tests were run before live integration was implemented.

For a repeatable real Chromium smoke test with the app already on port 8501:

```bash
work/.venv/bin/python -m pip install -r requirements-browser.txt
# Codex Cloud already provides /usr/bin/chromium. On another cloud runner only:
# work/.venv/bin/python -m playwright install chromium
work/.venv/bin/python -m scripts.browser_smoke --base-url http://127.0.0.1:8501
```

This browser test exercises demo research/downloads, uploads both input formats, checks every output hyperlink and input value, tests live-mode credential gating and takes desktop/mobile screenshots under ignored `work/browser-smoke/`. It does not call the real providers. `TEST_RESULTS.md` records what was actually run. `.github/workflows/tests.yml` runs the offline test suite and static checks on future pushes/PRs.

## Save to GitHub after review

**Review branch:** `feature/brand-intelligence-platform` is based on the existing `main` history. The source and validation reports are provided for review. No merge or application deployment has been performed. The original project introduction above is preserved.

For future changes, create a new branch from the latest main in the Codex Cloud terminal, make your changes, then review, commit and push them:

```bash
cd /workspace/Brand-Lit-Search-tool
git status --short
git fetch origin
git switch -c feature/your-next-change origin/main
# Make and review your changes before staging.
git add app.py brand_research tests scripts examples requirements.txt requirements-dev.txt requirements-browser.txt pyproject.toml README.md TEST_RESULTS.md .gitignore .streamlit/config.toml .streamlit/secrets.toml.example .github/workflows/tests.yml
git diff --cached --stat
git diff --cached
git commit -m "Build evidence-backed brand research platform"
git push -u origin feature/your-next-change
```

The origin is `https://github.com/shivangdwivediii/Brand-Lit-Search-tool.git`. The repository was empty at the initial build, but `main` now contains the project introduction. The implementation branch is based on that existing commit, so it can be reviewed in a pull request targeting `main`. Branch pushes must use normal, non-forced Git updates. Review and merge are separate user decisions; application deployment is also a separate action.

Alternatively, use **GitHub Codespaces** entirely in the browser, copy the reviewed source files into the repository, and commit them there. A supplied source ZIP is for review/transfer and should be extracted into the repository; uploading the ZIP itself does not create a runnable app. Do not include `work/`, API keys or real research workbooks in commits.

## Deploy to Streamlit Community Cloud when you choose

1. Save the reviewed source to a GitHub branch using the preceding steps.
2. In Streamlit Community Cloud, choose **Create app → GitHub repository**.
3. Select `shivangdwivediii/Brand-Lit-Search-tool`, your reviewed branch, and **`app.py`** as the main file.
4. Select **Python 3.12** in advanced settings and add keys in **Secrets** if you want live mode. Keep them blank to deploy a demo only. `requirements.txt` installs the runtime packages automatically; no laptop setup is required.
5. Choose the appropriate viewer/access settings. Deploy only when you are ready.
6. Run the fictional demo and download its workbook. Then upload a small real input with conservative limits to validate your keys, model access, provider quota and live results.

No external database, Docker, browser binary, local Excel installation or `packages.txt` is needed in production. Browser testing dependencies are separate and not installed for the Streamlit app. The code is ready for deployment, but an actual Community Cloud deployment and authenticated live-provider smoke test have not been performed.

## Repository layout

```text
app.py                       Streamlit interface
brand_research/
  config.py                  Server-side credential loading
  models.py                  Facts, sources, evidence and research records
  excel.py                   Input validation and hyperlink export
  demo.py                    Explicitly fictional offline fixtures
  limits.py                  Request/token budgets and safe provider errors
  providers.py               SerpApi + real OpenAI SDK integrations
  validation.py              Per-cell grounding and acquisition checks
  engine.py                  Fast/Deep workflows and private session cache
examples/                    Both example XLSX input formats
scripts/                     Example generation and browser smoke test
tests/                       Offline automated suite
.github/workflows/tests.yml   Review-branch CI
requirements*.txt            Runtime, unit-test and optional browser dependencies
.streamlit/                  Theme/config and placeholder secrets template
```
