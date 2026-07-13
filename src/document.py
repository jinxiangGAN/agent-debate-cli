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
            f"# 圆桌讨论：{topic}\n\n"
            "> 这是一份**共享讨论文档**，也是所有参与者的唯一真相源。\n"
            "> 每位参与者依次在文末追加署名发言；组织者负责主持与收敛。\n"
            "> 你（人类）可以随时直接编辑本文件，用 `## [你] ...` 追加发言——下一位参与者会读到。\n\n"
            f"开始时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
            "---\n"
        )
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(header)

    def read(self) -> str:
        """读全文——这就是喂给每个 agent 的讨论上下文。"""
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def next_seq(self) -> int:
        """扫描已有发言块的序号 `· #N ·`，返回下一个。"""
        seqs = [int(m) for m in re.findall(r"·\s*#(\d+)\s*·", self.read())]
        return (max(seqs) + 1) if seqs else 1

    def append(self, author: str, label: str, content: str) -> int:
        """追加一条署名发言块，返回它的序号。"""
        seq = self.next_seq()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        block = f"\n## [{author}] {label} · #{seq} · {ts}\n\n{content.strip()}\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(block)
        return seq
