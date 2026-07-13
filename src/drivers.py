"""把一个 CLI（codex / claude / mock）包装成"给 prompt、拿文本"的驱动。

CLI 每次调用无状态，所以每一轮都把共享文档全文塞进 prompt。
输出一边流式写进该 agent 的日志文件（tmux pane 用 tail -f 实时显示），
一边收集起来作为返回值。
"""
from __future__ import annotations
import os
import subprocess
from .config import DriverSpec


class Driver:
    def __init__(self, spec: DriverSpec, cwd: str | None = None):
        self.spec = spec
        self.cwd = cwd

    def _argv(self, prompt: str) -> list[str]:
        if self.spec.mode == "arg":
            return [c.replace("{prompt}", prompt) for c in self.spec.cmd]
        return list(self.spec.cmd)

    def invoke(self, prompt: str, log_path: str, timeout: int) -> str:
        argv = self._argv(prompt)
        use_stdin = self.spec.mode == "stdin"

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if use_stdin else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=self.cwd,
            env=os.environ.copy(),
        )
        if use_stdin:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()

        chunks: list[str] = []
        with open(log_path, "a", encoding="utf-8") as logf:
            assert proc.stdout is not None
            for line in proc.stdout:
                chunks.append(line)
                logf.write(line)
                logf.flush()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            note = "\n[driver] ⚠️ 调用超时，已终止。\n"
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(note)
            chunks.append(note)

        return "".join(chunks).strip()
