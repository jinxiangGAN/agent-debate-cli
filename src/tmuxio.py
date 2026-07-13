"""tmux 观众席：一个大 pane 实时 tail 共享的 DISCUSSION.md，
每个 agent 再各一个小 pane tail 它的原始输出流（方便看"打字"过程与调试）。
"""
from __future__ import annotations
import shlex
import subprocess


def _tmux(*args: str) -> str:
    return subprocess.run(
        ["tmux", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def available() -> bool:
    try:
        subprocess.run(["tmux", "-V"], check=True, capture_output=True)
        return True
    except Exception:
        return False


class TmuxWall:
    def __init__(self, session: str):
        self.session = session
        self._first = True

    def kill(self) -> None:
        subprocess.run(["tmux", "kill-session", "-t", self.session], capture_output=True)

    def add_pane(self, title: str, log_path: str) -> None:
        tail_cmd = (
            f"printf '\\033]2;{title}\\007'; "
            f"echo '=== {title} ==='; "
            f"touch {shlex.quote(log_path)}; "
            f"tail -n +1 -f {shlex.quote(log_path)}"
        )
        if self._first:
            self.kill()
            _tmux("new-session", "-d", "-s", self.session, "-x", "250", "-y", "60",
                  f"bash -lc {shlex.quote(tail_cmd)}")
            self._first = False
        else:
            _tmux("split-window", "-t", self.session, f"bash -lc {shlex.quote(tail_cmd)}")
        _tmux("select-layout", "-t", self.session, "tiled")
        _tmux("set-option", "-t", self.session, "-g", "pane-border-status", "top")
        _tmux("set-option", "-t", self.session, "-g", "pane-border-format", " #{pane_title} ")
