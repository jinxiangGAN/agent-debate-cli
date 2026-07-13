"""PR2 regression tests: --resume / non-destructive doc + context size warning."""
import pytest

from src.config import Config
from src.document import SharedDoc
from src.drivers import DriverResult
from src.orchestrator import Orchestrator


class _FakeDriver:
    def __init__(self, fn):
        self.fn = fn

    def invoke(self, prompt, log_path, timeout):
        open(log_path, "a").close()
        return self.fn(prompt)


def _fake(orch, organizer_fn, worker_fn):
    orch.organizer.driver = _FakeDriver(organizer_fn)
    for w in orch.workers:
        w.driver = _FakeDriver(worker_fn)


def test_resume_skips_completed_rounds(tmp_path):
    cfg = Config.load("config.mock.yaml")
    cfg.max_rounds = 2
    cfg.document = str(tmp_path / "D.md")

    # pre-build a doc with the opening and one complete round
    d = SharedDoc(cfg.document, cfg.topic)          # reset=True -> header
    d.append("chair", "Organizer · Opening", "opening")
    for w in ("alice", "bob", "carol"):
        d.append(w, "Round 1", "round-1 point")
    d.append("chair", "Organizer · Round 1 summary",
             'summary\n{"consensus_reached": "No", "reason": "r"}')

    orch = Orchestrator(cfg, str(tmp_path), reset=False)
    _fake(orch,
          lambda p: DriverResult('s\n{"consensus_reached": "No", "reason": "r"}', "ok"),
          lambda p: DriverResult("a point", "ok"))
    orch.run()

    text = open(cfg.document, encoding="utf-8").read()
    assert text.count("] Round 1 · #") == 3          # round 1 NOT re-run
    assert "] Round 2 · #" in text                    # resumed into round 2
    assert "Organizer · Final report" in text         # and finished


def test_resume_refuses_topic_mismatch(tmp_path):
    cfg = Config.load("config.mock.yaml")
    cfg.document = str(tmp_path / "D.md")
    d = SharedDoc(cfg.document, "a completely different topic")
    d.append("chair", "Organizer · Opening", "o")

    orch = Orchestrator(cfg, str(tmp_path), reset=False)
    with pytest.raises(ValueError):
        orch.run()


def test_resume_noop_when_already_complete(tmp_path):
    cfg = Config.load("config.mock.yaml")
    cfg.document = str(tmp_path / "D.md")
    d = SharedDoc(cfg.document, cfg.topic)
    d.append("chair", "Organizer · Opening", "o")
    d.append("chair", "Organizer · Final report", "done")

    orch = Orchestrator(cfg, str(tmp_path), reset=False)
    before = open(cfg.document, encoding="utf-8").read()
    orch.run()
    assert open(cfg.document, encoding="utf-8").read() == before   # untouched


def test_context_size_warning(tmp_path, capsys):
    cfg = Config.load("config.mock.yaml")
    cfg.context_warn_chars = 50            # tiny threshold -> the header alone trips it
    cfg.document = str(tmp_path / "D.md")
    orch = Orchestrator(cfg, str(tmp_path))
    _fake(orch,
          lambda p: DriverResult('s\n{"consensus_reached": "Yes", "reason": "r"}', "ok"),
          lambda p: DriverResult("x", "ok"))
    orch.run()
    assert "上下文已达" in capsys.readouterr().out
