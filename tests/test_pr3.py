"""PR3 tests: verdict-parse observability, non-convergence signal, config validation."""
import textwrap

import pytest

from src.config import Config, ConfigError
from src.drivers import DriverResult
from src.orchestrator import Orchestrator, _parse_verdict


# ---------- verdict parse: reached vs parsed_ok ----------

@pytest.mark.parametrize("text, reached, parsed_ok", [
    ('x\n{"consensus_reached": "Yes", "reason": "r"}', True, True),
    ('x\n{"consensus_reached": "No", "reason": "r"}', False, True),
    ('x\nnot json at all', False, False),
    ('x\n{"consensus_reached": "Maybe"}', False, False),
    ('', False, False),
])
def test_parse_verdict_flags(text, reached, parsed_ok):
    r, ok, _ = _parse_verdict(text)
    assert (r, ok) == (reached, parsed_ok)


# ---------- convergence signal + observability warn ----------

class _FakeDriver:
    def __init__(self, fn):
        self.fn = fn

    def invoke(self, prompt, log_path, timeout):
        open(log_path, "a").close()
        return self.fn(prompt)


def _wire(orch, organizer_fn):
    orch.organizer.driver = _FakeDriver(organizer_fn)
    for w in orch.workers:
        w.driver = _FakeDriver(lambda p: DriverResult("a point", "ok"))


def test_converged_true_on_consensus(tmp_path):
    cfg = Config.load("configs/mock.yaml")
    cfg.max_rounds = 3
    cfg.document = str(tmp_path / "D.md")
    orch = Orchestrator(cfg, str(tmp_path))
    _wire(orch, lambda p: DriverResult('s\n{"consensus_reached": "Yes", "reason": "r"}', "ok"))
    orch.run()
    assert orch.converged is True


def test_unparseable_verdict_warns_and_does_not_converge(tmp_path, capsys):
    cfg = Config.load("configs/mock.yaml")
    cfg.max_rounds = 2
    cfg.document = str(tmp_path / "D.md")
    orch = Orchestrator(cfg, str(tmp_path))
    _wire(orch, lambda p: DriverResult("no json verdict on the last line", "ok"))
    orch.run()
    assert orch.converged is False
    assert "could not parse the organizer verdict" in capsys.readouterr().err


# ---------- config validation ----------

def _cfg(tmp_path, body: str) -> str:
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)

_VALID = """
    topic: t
    drivers:
      m: {cmd: ["echo"], mode: stdin}
    organizer: {name: chair, driver: m, role: r}
    agents:
      - {name: a, driver: m, role: r}
"""


def test_valid_config_loads(tmp_path):
    Config.load(_cfg(tmp_path, _VALID))  # must not raise


@pytest.mark.parametrize("body, needle", [
    (_VALID.replace("topic: t", "language: en"), "missing required key: 'topic'"),
    (_VALID.replace("driver: m, role: r}\n    agents", "driver: nope, role: r}\n    agents"), "not defined in 'drivers'"),
    (_VALID.replace("mode: stdin", "mode: pipe"), "must be 'arg' or 'stdin'"),
    (_VALID.replace('cmd: ["echo"]', "cmd: []"), "must be a non-empty list"),
    (_VALID + "    max_rounds: 0\n", "'max_rounds' must be a positive integer"),
    (_VALID + "    context_file: does-not-exist.txt\n", "context_file not found"),
    (_VALID.replace("- {name: a, driver: m, role: r}",
                    "- {name: a, driver: m, role: r}\n      - {name: a, driver: m, role: r}"),
     "duplicate participant name"),
])
def test_invalid_config_raises_with_field_path(tmp_path, body, needle):
    with pytest.raises(ConfigError) as ei:
        Config.load(_cfg(tmp_path, body))
    assert needle in str(ei.value)


def test_context_file_resolved_relative_to_config(tmp_path):
    (tmp_path / "brief.md").write_text("BRIEF-CONTENT", encoding="utf-8")
    cfg = Config.load(_cfg(tmp_path, _VALID + '    context_file: brief.md\n'))
    assert "BRIEF-CONTENT" in cfg.context
