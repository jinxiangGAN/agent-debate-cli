"""Wraps a CLI (codex / claude / mock) into a "give prompt, get result" driver.

Each CLI call is stateless, so the full shared document is packed into the prompt every
round. Raw stdout is streamed to the agent's log file (live `tail -f` in a tmux pane);
`invoke()` returns a `DriverResult` with a clean/bounded text and a status.

PR1 reliability hardening (from the implementation-plan debate):
- A reader thread drains stdout and a writer thread feeds stdin concurrently, so a large
  prompt can't deadlock against the child's stdout (the pre-read stdin write used to hang,
  which also defeated the timeout).
- A single monotonic deadline == `per_turn_timeout` (total wall-clock budget). On expiry we
  kill the whole process group with bounded escalation: SIGTERM -> wait(grace) -> SIGKILL.
- timeout / non-zero exit -> status "timeout"/"error"; the `{outfile}` clean message is only
  trusted on a zero exit (a SIGKILLed codex may have flushed a partial file).
- The temp `{outfile}` is unlinked unconditionally; the captured diagnostic is bounded to a
  tail (so a chatty crash can't bloat the doc and every later prompt).

Clean-output mode: if `cmd` contains a `{outfile}` placeholder, we substitute a temp path and
read THAT file as the result (used for codex, whose stdout is full of banner/prompt-echo/logs).
"""
from __future__ import annotations
import os
import queue
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from .config import DriverSpec


_TAIL_LINES = 400  # bounded captured text: keeps a chatty crash from bloating the doc


@dataclass
class DriverResult:
    text: str           # clean final message (ok) or a bounded diagnostic tail (timeout/error)
    status: str         # "ok" | "timeout" | "error"
    error: str = ""     # short note when not ok

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Driver:
    def __init__(self, spec: DriverSpec, cwd: str | None = None, grace: float = 2.0):
        self.spec = spec
        self.cwd = cwd
        self.grace = grace  # seconds to wait after SIGTERM before SIGKILL (internal cap)

    def _argv(self, prompt: str, outfile: str | None) -> list[str]:
        argv = []
        for c in self.spec.cmd:
            if outfile is not None:
                c = c.replace("{outfile}", outfile)
            if self.spec.mode == "arg":
                c = c.replace("{prompt}", prompt)
            argv.append(c)
        return argv

    def invoke(self, prompt: str, log_path: str, timeout: int) -> DriverResult:
        uses_outfile = any("{outfile}" in c for c in self.spec.cmd)
        outfile: str | None = None
        if uses_outfile:
            fd, outfile = tempfile.mkstemp(suffix=".txt", prefix="agentmsg-")
            os.close(fd)
        try:
            return self._run(prompt, log_path, timeout, outfile)
        finally:
            if outfile is not None:            # unconditional temp-file cleanup
                try:
                    os.unlink(outfile)
                except OSError:
                    pass

    def _run(self, prompt: str, log_path: str, timeout: int, outfile: str | None) -> DriverResult:
        argv = self._argv(prompt, outfile)
        use_stdin = self.spec.mode == "stdin"
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if use_stdin else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=self.cwd,
                env=os.environ.copy(),
                start_new_session=True,        # own process group so we can killpg
            )
        except (OSError, ValueError) as e:
            return DriverResult(text="", status="error", error=f"spawn failed: {e}")

        q: "queue.Queue[str | None]" = queue.Queue()

        def _reader() -> None:
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    q.put(line)
            except (OSError, ValueError):
                pass
            finally:
                q.put(None)  # sentinel: stdout closed

        def _writer() -> None:
            if not use_stdin:
                return
            try:
                assert proc.stdin is not None
                proc.stdin.write(prompt)
            except (OSError, ValueError):
                pass
            finally:
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except (OSError, ValueError):
                    pass

        reader = threading.Thread(target=_reader, name="driver-reader", daemon=True)
        writer = threading.Thread(target=_writer, name="driver-writer", daemon=True)
        reader.start()
        writer.start()

        deadline = time.monotonic() + timeout
        tail: "deque[str]" = deque(maxlen=_TAIL_LINES)
        timed_out = False

        with open(log_path, "a", encoding="utf-8") as logf:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    line = q.get(timeout=remaining)
                except queue.Empty:
                    timed_out = True
                    break
                if line is None:
                    break  # stdout closed normally
                tail.append(line)
                logf.write(line)
                logf.flush()

        if timed_out:
            self._kill(proc)
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write("\n[driver] ⚠️ call timed out, process group killed.\n")
            self._join(reader, writer)
            return DriverResult(text="".join(tail).strip(), status="timeout", error="timeout")

        # stdout closed -> reap for the exit code (process should be exiting)
        try:
            code = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            self._kill(proc)
            self._join(reader, writer)
            return DriverResult(text="".join(tail).strip(), status="timeout",
                                error="timeout after stdout close")

        self._join(reader, writer)
        captured = "".join(tail).strip()

        if code != 0:
            return DriverResult(text=captured, status="error", error=f"exit code {code}")

        # zero exit: trust the clean outfile if the driver produced one
        if outfile is not None:
            try:
                with open(outfile, "r", encoding="utf-8") as f:
                    msg = f.read().strip()
            except OSError:
                msg = ""
            if msg:
                return DriverResult(text=msg, status="ok")
            # empty outfile on a clean exit -> fall back to captured stdout
        return DriverResult(text=captured, status="ok")

    def _kill(self, proc: "subprocess.Popen") -> None:
        """Bounded escalation: SIGTERM -> wait(grace) -> SIGKILL -> reap."""
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            pgid = None

        def _sig(sig: int) -> None:
            try:
                if pgid is not None:
                    os.killpg(pgid, sig)
                else:
                    proc.send_signal(sig)
            except OSError:
                pass

        _sig(signal.SIGTERM)
        try:
            proc.wait(timeout=self.grace)
            return
        except subprocess.TimeoutExpired:
            pass
        _sig(signal.SIGKILL)
        try:
            proc.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def _join(*threads: threading.Thread) -> None:
        for t in threads:
            t.join(0.5)  # daemon threads; a wedged OS-pipe write won't block process exit
