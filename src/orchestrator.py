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
    """从组织者小结里抽出末尾的 JSON 裁决，返回 (是否收敛, 理由)。

    容错：找不到 JSON 时，退化为关键词匹配；再不行就当作"继续"。
    """
    matches = re.findall(r"\{[^{}]*consensus_reached[^{}]*\}", text, re.DOTALL)
    if matches:
        try:
            obj = json.loads(matches[-1])
            reached = str(obj.get("consensus_reached", "")).strip().lower() in ("yes", "true", "1")
            return reached, str(obj.get("reason", ""))
        except json.JSONDecodeError:
            pass
    low = text.lower()
    if '"consensus_reached": "yes"' in low or "consensus_reached: yes" in low:
        return True, "(从文本推断)"
    return False, "(未解析到裁决，默认继续)"


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

    def _maybe_human_turn(self, round_no: int) -> None:
        if not self.interactive:
            return
        try:
            note = self._human_input(
                f"\n  [第 {round_no} 轮结束] 想插话吗？直接输入一句话，或直接回车跳过（也可去编辑 DISCUSSION.md）：\n  > "
            ).strip()
        except EOFError:
            note = ""
        if note:
            self.doc.append("你", f"第 {round_no} 轮后·人类补充", note)

    def run(self) -> str:
        c = self.cfg

        # 1) 组织者开场
        opening = self.organizer.run(
            "开场",
            prompts.organizer_opening(
                c.organizer.role, c.topic, c.language,
                self.doc.read(), [w.name for w in self.workers],
            ),
            c.per_turn_timeout,
        )
        self.doc.append(self.organizer.name, "组织者·开场", opening)

        # 2) 多轮讨论
        for round_no in range(1, c.max_rounds + 1):
            for w in self.workers:
                reply = w.run(
                    f"第 {round_no} 轮发言",
                    prompts.agent_turn(
                        w.spec.role, c.topic, c.language,
                        self.doc.read(), c.turn_word_limit, w.name,
                    ),
                    c.per_turn_timeout,
                )
                self.doc.append(w.name, f"第 {round_no} 轮", reply)

            review = self.organizer.run(
                f"第 {round_no} 轮裁决",
                prompts.organizer_review(
                    c.organizer.role, c.topic, c.language,
                    self.doc.read(), round_no, c.max_rounds,
                ),
                c.per_turn_timeout,
            )
            self.doc.append(self.organizer.name, f"组织者·第 {round_no} 轮小结", review)

            reached, _ = _parse_verdict(review)
            if reached:
                break
            self._maybe_human_turn(round_no)

        # 3) 组织者最终收尾
        final = self.organizer.run(
            "最终结论",
            prompts.organizer_final(c.organizer.role, c.topic, c.language, self.doc.read()),
            c.per_turn_timeout,
        )
        self.doc.append(self.organizer.name, "组织者·最终结论", final)
        return self.doc.path
