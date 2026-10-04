from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_start_script_exists_and_uses_project_root():
    script = ROOT / "scripts" / "start.sh"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "PROJECT_ROOT" in text
    assert "review-server.pid" in text


def test_stop_script_does_not_use_broad_process_kill():
    script = ROOT / "scripts" / "stop.sh"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "review-server.pid" in text
    assert "pkill" not in text
    assert "killall" not in text
