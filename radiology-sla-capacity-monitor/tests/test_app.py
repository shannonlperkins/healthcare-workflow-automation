from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_and_coverage_scenario():
    path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(path), default_timeout=45).run()
    assert not app.exception
    assert not app.error
    assert len(app.tabs) == 2
    assert any(m.label == "Expected SLA misses" for m in app.metric)
    baseline = float(next(m.value for m in app.metric if m.label == "Expected SLA misses"))
    activate = next(w for w in app.multiselect if "cover full window" in w.label)
    activate.set_value(["Dr. Brooks"])
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    scenario = float(next(m.value for m in app.metric if m.label == "Expected SLA misses"))
    assert scenario < baseline
    assert any("scenario changes" in i.value for i in app.info)
    remove = next(w for w in app.multiselect if "remove reader" in w.label)
    remove.set_value(["Dr. Brooks"])
    app.button[0].click().run()
    assert "Choose separate readers" in app.error[0].value
