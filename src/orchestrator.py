"""编排逻辑：组织者主持，N 个讨论者轮流在共享文档里发言，多轮直到收敛或轮数用尽。

结构借鉴 MAD 的 Debate.run：init（开场）→ 每轮各方发言 → moderator 评估 →
收敛则结束，否则继续 → 最终定论。区别是发言的"广播"落地为写入共享 DISCUSSION.md，
且 moderator 用 JSON 裁决是否收敛。
"""
from __future__ import annotations
import json
import re
import sys

from .config import Config
from .agent import Agent
from .drivers import Driver
from .document import SharedDoc
from . import prompts


def _parse_verdict(text: str) -> tuple[bool, bool, str]:
    """裁决解析：取**最后一非空行**做 json.loads，校验 consensus_reached 精确 ∈ {Yes,No}。

    返回 (reached, parsed_ok, detail)：
    - parsed_ok=True  -> 成功解析出合法裁决；reached 为 Yes/No，detail 是 reason。
    - parsed_ok=False -> 解析/校验失败（宁可当 No 也不假收敛）；detail 是诊断信息。
      区分这两者，是为了只在**真正失败**时告警，而不是把合法的 "No" 也当异常。
    """
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return False, False, f"last non-empty line is not JSON: {line[:160]}"
        if not isinstance(obj, dict):
            return False, False, "verdict JSON is not an object"
        val = str(obj.get("consensus_reached", "")).strip()
        if val not in ("Yes", "No"):
            return False, False, f"invalid consensus_reached value: {val!r}"
        return val == "Yes", True, str(obj.get("reason", ""))
    return False, False, "empty verdict (no JSON line found)"


class Orchestrator:
    def __init__(self, cfg: Config, log_dir: str, interactive: bool = False,
                 human_input=input, reset: bool = True):
        self.cfg = cfg
        self.log_dir = log_dir
        self.interactive = interactive
        self._human_input = human_input
        self.reset = reset
        self._warned_size = False
        self.converged = False   # True once a round reaches consensus (or resume finds a final report)
        self.doc = SharedDoc(cfg.document, cfg.topic, reset=reset)

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

    def _context(self) -> str:
        """读文档全文（即喂给下一个 prompt 的上下文），过大时只读地告警一次。"""
        text = self.doc.read()
        limit = self.cfg.context_warn_chars
        if limit and len(text) > limit and not self._warned_size:
            self._warned_size = True
            print(f"  ⚠️ 上下文已达 {len(text):,} 字符（阈值 {limit:,}）——"
                  f"每轮都会把全文发给每个 agent，token 成本随之上升。"
                  f"可调小 max_rounds/turn_word_limit，或分拆议题。", flush=True)
        return text

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

        # 0) Resume vs fresh. Resume only from a doc with a matching topic; skip the
        #    opening and any already-complete rounds. Never infer partial turn-status.
        resuming = (not self.reset) and self.doc.has_opening()
        if resuming:
            existing_topic = self.doc.header_topic()
            if existing_topic != c.topic:
                raise ValueError(
                    f"cannot resume: document topic {existing_topic!r} != config topic {c.topic!r}")
            if self.doc.has_final_report():
                print("  ✔️ 该讨论已有最终报告，无需续跑。", flush=True)
                self.converged = True
                return self.doc.path
            start_round = self.doc.count_round_summaries() + 1
            print(f"  ↻ resume：已完成 {start_round - 1} 轮，从第 {start_round} 轮继续。", flush=True)
        else:
            start_round = 1
            # Background material, then the organizer opening (fresh run only)
            if c.context.strip():
                self.doc.append("Background", "for reference", c.context.strip())
            opening = self.organizer.run(
                "Opening",
                prompts.organizer_opening(
                    c.organizer.role, c.topic, c.language,
                    self._context(), [w.name for w in self.workers],
                ),
                c.per_turn_timeout,
            )
            self._append_result(self.organizer.name, "Organizer · Opening", opening)

        # 2) Debate rounds
        for round_no in range(start_round, c.max_rounds + 1):
            round_failed = False
            for w in self.workers:
                reply = w.run(
                    f"Round {round_no}",
                    prompts.agent_turn(
                        w.spec.role, c.topic, c.language,
                        self._context(), c.turn_word_limit, w.name,
                    ),
                    c.per_turn_timeout,
                )
                if not self._append_result(w.name, f"Round {round_no}", reply):
                    round_failed = True

            review = self.organizer.run(
                f"Round {round_no} verdict",
                prompts.organizer_review(
                    c.organizer.role, c.topic, c.language,
                    self._context(), round_no, c.max_rounds,
                ),
                c.per_turn_timeout,
            )
            review_ok = self._append_result(
                self.organizer.name, f"Organizer · Round {round_no} summary", review)

            # A round with a failed turn can never converge (avoid false consensus on a
            # crippled round); a failed organizer review also can't declare Yes.
            if review_ok:
                reached, parsed_ok, detail = _parse_verdict(review.text)
                if not parsed_ok:
                    # Observability floor: a silent parse failure would burn every round
                    # (and full-doc tokens) forever without ever converging. Surface it.
                    print(f"  ⚠️ round {round_no}: could not parse the organizer verdict "
                          f"({detail}) — treating as 'No'.", file=sys.stderr, flush=True)
            else:
                reached = False
            if review_ok and reached and not round_failed:
                self.converged = True
                break
            self._maybe_human_turn(round_no)

        # 3) Organizer final report
        final = self.organizer.run(
            "Final report",
            prompts.organizer_final(c.organizer.role, c.topic, c.report_language, self._context()),
            c.per_turn_timeout,
        )
        self._append_result(self.organizer.name, "Organizer · Final report", final)
        return self.doc.path
