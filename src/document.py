"""SharedDoc —— 共享讨论文档，既是"广播总线"也是最终产物。

借鉴 MAD 的 broadcast 思路：MAD 里每个人发言会广播进其他人的记忆；
这里把"广播"落地成写入同一份 DISCUSSION.md——所有 agent 每轮都读它的**当前全文**，
所以人类随时手改这份文件插话，下一位 agent 就能读到。
"""
from __future__ import annotations
import os
import re
from datetime import datetime


class SharedDoc:
    def __init__(self, path: str, topic: str, reset: bool = True):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if reset or not os.path.exists(path):
            self._init_doc(topic)

    def _init_doc(self, topic: str) -> None:
        header = (
            f"# Roundtable debate: {topic}\n\n"
            "> This is a **shared discussion document** and the single source of truth.\n"
            "> Each participant appends a signed contribution in turn; the organizer chairs and converges.\n"
            "> You (human) can edit this file anytime — add `## [You] ...` and the next participant will read it.\n\n"
            f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
            "---\n"
        )
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(header)

    def read(self) -> str:
        """读全文——这就是喂给每个 agent 的讨论上下文。"""
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    # ---- resume introspection：只认 harness 自有的标题/H1，不推断 turn-status ----

    def header_topic(self) -> str | None:
        """从 H1 `# Roundtable debate: <topic>` 解析出议题，供 resume 校验。"""
        for line in self.read().splitlines():
            if line.startswith("# Roundtable debate: "):
                return line[len("# Roundtable debate: "):].strip()
        return None

    def _labels(self) -> list[str]:
        return re.findall(r"^## \[.*?\] (.*?) · #\d+ · ", self.read(), re.MULTILINE)

    def has_opening(self) -> bool:
        return "Organizer · Opening" in self._labels()

    def has_final_report(self) -> bool:
        return "Organizer · Final report" in self._labels()

    def count_round_summaries(self) -> int:
        """有几轮是**完整完成**的（有非失败的 organizer 小结）——resume 的轮界。"""
        return sum(1 for lbl in self._labels()
                   if re.fullmatch(r"Organizer · Round \d+ summary", lbl))

    # Only real harness-written heading lines look like: "## [author] label · #N · ts".
    # Parsing the sequence from *heading lines only* means a body containing "· #99 ·"
    # can no longer poison next_seq (the #13 -> #100 bug seen in real runs).
    _HEADING_RE = re.compile(r"^## \[.*?\].* · #(\d+) · ", re.MULTILINE)

    def next_seq(self) -> int:
        """下一个序号：只扫 harness 自有的标题行，不看正文。"""
        seqs = [int(m) for m in self._HEADING_RE.findall(self.read())]
        return (max(seqs) + 1) if seqs else 1

    @staticmethod
    def _sanitize(content: str) -> str:
        """中和正文里两种 harness 自有语法，防止模型伪造归属/毒化序号：
        - 行首的 `## [`（伪造发言块标题）-> 前缀反斜杠转义
        - `· #<数字> ·`（序号标记）-> 打断该模式（虽然 next_seq 已只读标题，双保险）
        """
        out = []
        for line in content.splitlines():
            if re.match(r"\s{0,3}## \[", line):
                line = "\\" + line.lstrip()
            line = re.sub(r"(·\s*#)(\d+\s*·)", "\\1​\\2", line)  # ZWSP breaks the seq grammar
            out.append(line)
        return "\n".join(out)

    def append(self, author: str, label: str, content: str) -> int:
        """追加一条署名发言块（正文经清洗），返回它的序号。"""
        seq = self.next_seq()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        body = self._sanitize(content.strip())
        block = f"\n## [{author}] {label} · #{seq} · {ts}\n\n{body}\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(block)
        return seq
