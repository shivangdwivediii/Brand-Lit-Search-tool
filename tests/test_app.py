from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_app_demo_end_to_end_and_rerun_cache(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not app.exception
    app.button(key="start_research").click().run()
    assert not app.exception
    assert app.session_state["completed_run"]["usage"]["searches"] == 0
    assert len(app.session_state["completed_run"]["workbook"]) > 1000
    assert app.metric[0].value == "10/15"
    app.button(key="start_research").click().run()
    assert not app.exception
    assert all(r.cache_hit for r in app.session_state["completed_run"]["results"])


def test_live_mode_without_keys_is_disabled(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.radio(key="data_mode").set_value("Live research").run()
    assert not app.exception
    assert app.button(key="start_research").disabled
    assert any("SERPAPI_API_KEY" in warning.value for warning in app.warning)
