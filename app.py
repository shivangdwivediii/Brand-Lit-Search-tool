"""Streamlit entry point. Run in Codex Cloud or Streamlit Community Cloud."""

import hashlib

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from brand_research.config import load_settings
from brand_research.engine import ResearchEngine, SessionCache
from brand_research.excel import (
    MIME,
    InputError,
    example_workbook,
    export_workbook,
    read_input,
    results_frame,
)
from brand_research.limits import Budget
from brand_research.models import FIELDS
from brand_research.providers import OpenAIExtractor, SerpApiSearch

st.set_page_config(page_title="BrandLit · Brand Research", page_icon="🔎", layout="wide")
st.markdown(
    """<style>
.block-container {max-width: 1250px; padding-top: 3.5rem;}
[data-testid="stSidebar"] {border-right: 1px solid #dce5dc;}
div[data-testid="stMetric"] {border:1px solid #dce5dc; border-radius:12px; padding:14px;}
.eyebrow {font-size:.78rem; letter-spacing:.18em; color:#157f73; font-weight:700;}
.intro {color:#5e716b; font-size:1.08rem; max-width:760px; margin-bottom:1.5rem;}
</style>""",
    unsafe_allow_html=True,
)

try:
    server_secrets = st.secrets.to_dict()
except (StreamlitSecretNotFoundError, FileNotFoundError):
    server_secrets = {}
settings = load_settings(server_secrets)

if "research_cache" not in st.session_state:
    st.session_state.research_cache = SessionCache()

with st.sidebar:
    st.markdown("### ◉ BrandLit")
    st.caption("A source behind every finding.")
    st.divider()
    data_mode = st.radio("Data mode", ["Demo · no API keys", "Live research"], key="data_mode")
    demo = data_mode.startswith("Demo")
    mode = st.radio("Research depth", ["Fast", "Deep"], horizontal=True, key="research_depth")
    st.caption(
        "Fast: up to 5 Google searches + 1 AI extraction per brand. Deep: up to 10 searches + 2 extractions, including recent ownership checks."
    )
    with st.expander("API limits per run", expanded=False):
        max_searches = st.number_input(
            "Maximum Google searches", min_value=0, max_value=500, value=30, step=5
        )
        max_ai = st.number_input(
            "Maximum OpenAI requests", min_value=0, max_value=100, value=6, step=1
        )
        max_tokens = st.number_input(
            "Maximum OpenAI tokens", min_value=0, max_value=2_000_000, value=100_000, step=10_000
        )
        st.caption(
            "Hard request caps include failed attempts. Token reservations include an upper bound on input and output; failed calls retain their reservation. Provider billing is authoritative. No automatic retries."
        )
    st.divider()
    st.caption("SERVER CREDENTIALS")
    st.write(
        ("✓" if settings.serpapi_key else "○")
        + " SerpApi "
        + ("configured" if settings.serpapi_key else "not configured")
    )
    st.write(
        ("✓" if settings.openai_key else "○")
        + " OpenAI "
        + ("configured" if settings.openai_key else "not configured")
    )
    st.caption(f"Model: {settings.model}")
    if st.button("Clear session cache", width="stretch", key="clear_cache"):
        st.session_state.research_cache.clear()
        st.toast("Session research cache cleared")
    st.caption("Cache: this session only · 6-hour expiry · no disk storage")

st.markdown(
    '<div class="eyebrow">BRAND INTELLIGENCE / RESEARCH WORKSPACE</div>', unsafe_allow_html=True
)
st.title("Every brand has a beginning.")
st.markdown(
    '<div class="intro">Find who launched a brand, where it began, and how ownership changed. Take the evidence with you in a source-linked Excel workbook.</div>',
    unsafe_allow_html=True,
)

if demo:
    st.info(
        "Demo workspace · Fictional brands and reserved .example source URLs. No API calls or real-world verification."
    )
else:
    st.info(
        "Live research uses public Google excerpts. Findings are automatically checked against cited excerpts; review the source pages before relying on them."
    )

workspace, guide = st.tabs(["Research workspace", "How it works"])
with guide:
    st.markdown("""
1. **Bring your brand list.** Upload an `.xlsx` workbook with **Brand** and **Parent Company** or **Category**. Both can be included. All original columns and row order are preserved as values. The first worksheet is used, with up to 200 rows, 50 columns and a 10 MB file limit. Formula cells are rejected; paste values first.
2. **Choose a research depth.** Fast searches history, business profiles and ownership. Deep adds official-domain searches, recent transactions, controlling-owner research and a second extraction. Search excerpts can be incomplete or stale in either mode.
3. **Inspect the evidence.** Each accepted value needs an exact source ID, a verbatim supporting excerpt and high-confidence extraction. Founding means the brand's founding, not the parent's incorporation. The launching company is distinct from the current owner.
4. **Download your workbook.** Every supported researched cell has its own direct source hyperlink and a comment with evidence. The Research Log includes source excerpts, search queries, rejected citations, errors, cache use and usage counts. “Unable to verify” cells have no link.

**Acquisition rules.** We research the latest completed controlling acquisition of the brand or its owner, excluding minority investments and pending deals. “Not acquired” requires explicit evidence of never-acquired or continuing independent ownership history, two independent publisher domains including a preferred source, and completed acquisition searches. Missing results and API failures are insufficient.

**Source priority.** Official brand/company domain candidates → public LinkedIn company pages, Bloomberg, Crunchbase → Tracxn, PitchBook → corporate filings → reputable press → Wikipedia → wider research. Domain priority is a heuristic; the extraction must also match the brand identity. Only public SerpApi excerpts are read. No login, paywall bypass, source-page scraping or personal LinkedIn profiles.

**Privacy and cost.** Live research sends brand names and Parent Company/Category context to SerpApi and OpenAI. Other uploaded columns are not sent. Credentials come from server environment variables or Streamlit secrets. Uploads, downloads and caches stay in session memory; there is no application disk persistence. Close the session to release them. Session caching is private and expires after six hours; cache hits retain the original evidence timestamp. A new session/run has fresh limits, so also configure billing caps with both providers.
""")
    st.code(
        'SERPAPI_API_KEY = "your-key"\nOPENAI_API_KEY = "your-key"\nOPENAI_MODEL = "gpt-4o-mini"',
        language="toml",
    )
    st.caption(
        "For Streamlit Community Cloud: add these in App settings → Secrets. Never place real keys in GitHub."
    )

with workspace:
    left, right = st.columns([2, 1], gap="large")
    with left:
        st.subheader("1. Add your brands")
        input_choice = st.radio(
            "Input source",
            ["Try fictional example", "Upload Excel"],
            horizontal=True,
            key="input_source",
        )
        context_choice = st.selectbox(
            "Example context column",
            ["Parent Company", "Category"],
            disabled=input_choice == "Upload Excel",
        )
        uploaded = st.file_uploader(
            "Upload brand workbook",
            type=["xlsx"],
            disabled=input_choice != "Upload Excel",
            help="Use Brand + Parent Company or Brand + Category in the first worksheet.",
        )
    with right:
        st.subheader("Example workbooks")
        st.caption(
            "Three fictional brands: an acquired brand, an independent brand, and an unresolved brand."
        )
        st.download_button(
            "↓ Brand + Parent Company",
            example_workbook("Parent Company"),
            "example_parent_company.xlsx",
            MIME,
            on_click="ignore",
            width="stretch",
        )
        st.download_button(
            "↓ Brand + Category",
            example_workbook("Category"),
            "example_category.xlsx",
            MIME,
            on_click="ignore",
            width="stretch",
        )

    payload = (
        example_workbook(context_choice)
        if input_choice == "Try fictional example"
        else uploaded.getvalue()
        if uploaded
        else None
    )
    frame = None
    if payload:
        try:
            frame = read_input(payload)
        except InputError as exc:
            st.error(str(exc))
    if frame is not None:
        st.dataframe(frame.astype("string").fillna(""), hide_index=True, width="stretch")
        st.caption(f"{len(frame)} input rows · {len(frame.columns)} original columns retained")
    elif not payload:
        st.caption("Choose an Excel file to preview your brands.")

    st.subheader("2. Research & verify")
    eligible = frame is not None
    if not demo and not settings.ready:
        st.warning(
            "Live research needs SERPAPI_API_KEY and OPENAI_API_KEY in server environment variables or Streamlit secrets. You can test the entire demo without keys."
        )
        eligible = False
    if not demo and input_choice == "Try fictional example":
        st.caption(
            "Upload your real brands to run live research. The example brands are fictional."
        )
        eligible = False
    if frame is not None:
        searches, ai = (5, 1) if mode == "Fast" else (10, 2)
        if demo:
            st.caption(
                "This run uses offline fixtures: 0 Google searches · 0 OpenAI calls · 0 tokens."
            )
        else:
            st.caption(
                f"Before caching: up to {len(frame) * searches} Google searches and {len(frame) * ai} OpenAI requests. Your run caps: {max_searches} searches, {max_ai} AI calls, {max_tokens:,} tokens. Caps can leave some rows unverified."
            )

    signature = hashlib.sha256(
        (payload or b"") + f"{demo}/{mode}/{settings.model}".encode()
    ).hexdigest()
    if st.button(
        "Start research",
        type="primary",
        disabled=not eligible,
        width="stretch",
        key="start_research",
    ):
        budget = Budget(int(max_searches), int(max_ai), int(max_tokens))
        engine = ResearchEngine(
            search=None if demo else SerpApiSearch(settings, budget),
            extractor=None if demo else OpenAIExtractor(settings, budget),
            budget=budget,
            cache=st.session_state.research_cache,
            model=settings.model,
        )
        bar = st.progress(0.0, text="Preparing research")
        with st.status("Researching your brands…", expanded=True) as status:
            current = st.empty()

            def progress(done, total, message):
                bar.progress(done / total, text=f"{done}/{total} brands complete")
                current.write(message)

            results = engine.run(frame, mode, demo, progress)
            workbook = export_workbook(frame, results, budget.snapshot())
            st.session_state.completed_run = {
                "signature": signature,
                "results": results,
                "output": results_frame(frame, results),
                "workbook": workbook,
                "usage": budget.snapshot(),
            }
            status.update(
                label="Research complete — workbook ready", state="complete", expanded=False
            )

    run = st.session_state.get("completed_run")
    if run and run["signature"] == signature:
        st.divider()
        st.subheader("3. Your findings")
        results, usage = run["results"], run["usage"]
        supported = sum(
            f.value is not None and bool(f.evidence) for r in results for f in r.facts.values()
        )
        total = len(results) * len(FIELDS)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Demo values" if demo else "Supported values", f"{supported}/{total}")
        c2.metric("Unable to verify", total - supported)
        c3.metric("Google / OpenAI calls", f"{usage['searches']} / {usage['ai_calls']}")
        c4.metric("Cache hits", sum(r.cache_hit for r in results))
        st.caption(
            f"OpenAI tokens charged to run budget: {usage['tokens']:,}. Failed requests retain conservative reservations. All research timestamps in the workbook are UTC."
        )
        st.download_button(
            "↓ Download researched Excel workbook",
            run["workbook"],
            "brand_research_demo.xlsx" if demo else "brand_research.xlsx",
            MIME,
            type="primary",
            on_click="ignore",
            width="stretch",
        )
        findings, evidence_tab = st.tabs(["Findings", "Evidence & activity"])
        with findings:
            st.dataframe(
                run["output"].astype("string").fillna(""), hide_index=True, width="stretch"
            )
            st.caption(
                "Open the downloaded Excel file to use per-cell source hyperlinks and evidence comments."
            )
        with evidence_tab:
            selected = st.selectbox(
                "Inspect a brand",
                range(len(results)),
                format_func=lambda i: f"{i + 1}. {results[i].brand or '(blank brand)'}",
            )
            result = results[selected]
            for note in result.notes:
                st.warning(note)
            rows = []
            sources = {s.id: s for s in result.sources}
            for key, label in FIELDS.items():
                fact = result.facts[key]
                for e in fact.evidence:
                    source = sources[e.source_id]
                    rows.append(
                        {
                            "Field": label,
                            "Value": str(fact.value),
                            "Source": source.url,
                            "Evidence": e.quote,
                        }
                    )
            if rows:
                st.dataframe(
                    rows,
                    hide_index=True,
                    width="stretch",
                    column_config={"Source": st.column_config.LinkColumn("Source")},
                )
            else:
                st.caption("No supported evidence was found for this row.")
            st.dataframe(result.events, hide_index=True, width="stretch")
    elif run:
        st.caption(
            "Inputs or research settings changed. Start research to generate a workbook for the current selection."
        )

st.divider()
st.caption(
    "BrandLit · Evidence-led brand research · Python + Streamlit · Review automated findings before use"
)
