"""编排逻辑：组织者主持，N 个讨论者轮流在共享文档里发言，多轮直到收敛或轮数用尽。

结构借鉴 MAD 的 Debate.run：init（开场）→ 每轮各方发言 → moderator 评估 →
收敛则结束，否则继续 → 最终定论。区别是发言的"广播"落地为写入共享 DISCUSSION.md，
且 moderator 用 JSON 裁决是否收敛。
"""
from __future__ import annotations
import json
import re

from .config import Config
from .agent import Agent
from .drivers import Driver
from .document import SharedDoc
from . import prompts


def _parse_verdict(text: str) -> tuple[bool, str]:
    """裁决解析：取**最后一非空行**做 json.loads，校验 consensus_reached 精确 ∈ {Yes,No}。

    prompt 已要求把 JSON 单独放在最后一行，所以不再用会漏嵌套花括号的正则；
    解析失败一律返回 (False, 诊断)——宁可多讨论一轮，也不要静默假收敛。
    """
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return False, f"verdict parse failed (last non-empty line is not JSON): {line[:160]}"
        if not isinstance(obj, dict):
            return False, "verdict JSON is not an object"
        val = str(obj.get("consensus_reached", "")).strip()
        if val not in ("Yes", "No"):
            return False, f"invalid consensus_reached value: {val!r}"
        return val == "Yes", str(obj.get("reason", ""))
    return False, "empty verdict"


class Orchestrator:
    def __init__(self, cfg: Config, log_dir: str, interactive: bool = False,
                 human_input=input):
        self.cfg = cfg
        self.log_dir = log_dir
        self.interactive = interactive
        self._human_input = human_input
        self.doc = SharedDoc(cfg.document, cfg.topic, reset=True)

        drivers = {name: Driver(spec) for name, spec in cfg.drivers.items()}
        self.organizer = Agent(cfg.organizer, drivers[cfg.organizer.driver], log_dir)
        self.workers = [Agent(a, drivers[a.driver], log_dir) for a in cfg.agents]

    def _all_agents(self) -> list[Agent]:
        return [self.organizer, *self.workers]

    def agent_log_paths(self) -> list[tuple[str, str]]:
        """给 tmux 用：[(标题, 路径), ...]。第一个是共享文档本身。"""
        panes = [("DISCUSSION.md", self.doc.path)]
        panes += [(a.name, a.log_path) for a in self._all_agents()]
        return panes

    def _append_result(self, author: str, label: str, result) -> bool:
        """把一次调用的结果写进文档。ok -> 正常发言；否则 -> 带标签的失败记录。
        返回 True 表示 ok。所有调用（含组织者/最终报告）都走这里，堵住"特权发言者"绕过。
        """
        if result.ok:
            self.doc.append(author, label, result.text)
            return True
        body = f"⚠️ turn failed (status={result.status}): {result.error}"
        if result.text:
            body += f"\n\nCaptured output (tail):\n{result.text}"
        self.doc.append(author, f"{label} · FAILED", body)
        return False

    def _maybe_human_turn(self, round_no: int) -> None:
        if not self.interactive:
            return
        try:
            note = self._human_input(
                f"\n  [end of round {round_no}] Want to chime in? Type a line, or press Enter to skip "
                f"(you can also edit DISCUSSION.md directly):\n  > "
            ).strip()
        except EOFError:
            note = ""
        if note:
            self.doc.append("You", f"Human note after round {round_no}", note)

    def run(self) -> str:
        c = self.cfg

        # 0) Optional background material: written first so every agent reads it
        if c.context.strip():
            self.doc.append("Background", "for reference", c.context.strip())

        # 1) Organizer opening
        opening = self.organizer.run(
            "Opening",
            prompts.organizer_opening(
                c.organizer.role, c.topic, c.language,
                self.doc.read(), [w.name for w in self.workers],
            ),
            c.per_turn_timeout,
        )
        self._append_result(self.organizer.name, "Organizer · Opening", opening)

        # 2) Debate rounds
        for round_no in range(1, c.max_rounds + 1):
            round_failed = False
            for w in self.workers:
                reply = w.run(
                    f"Round {round_no}",
                    prompts.agent_turn(
                        w.spec.role, c.topic, c.language,
                        self.doc.read(), c.turn_word_limit, w.name,
                    ),
                    c.per_turn_timeout,
                )
                if not self._append_result(w.name, f"Round {round_no}", reply):
                    round_failed = True

            review = self.organizer.run(
                f"Round {round_no} verdict",
                prompts.organizer_review(
                    c.organizer.role, c.topic, c.language,
                    self.doc.read(), round_no, c.max_rounds,
                ),
                c.per_turn_timeout,
            )
            review_ok = self._append_result(
                self.organizer.name, f"Organizer · Round {round_no} summary", review)

            # A round with a failed turn can never converge (avoid false consensus on a
            # crippled round); a failed organizer review also can't declare Yes.
            parsed, _ = _parse_verdict(review.text) if review_ok else (False, "review failed")
            reached = review_ok and parsed and not round_failed
            if reached:
                break
            self._maybe_human_turn(round_no)

        # 3) Organizer final report
        final = self.organizer.run(
            "Final report",
            prompts.organizer_final(c.organizer.role, c.topic, c.report_language, self.doc.read()),
            c.per_turn_timeout,
        )
        self._append_result(self.organizer.name, "Organizer · Final report", final)
        return self.doc.path
