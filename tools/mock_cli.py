#!/usr/bin/env python3
"""Fake CLI for zero-cost testing of the orchestration (spends no tokens).

Reads the prompt from stdin, decides which kind of turn it is from the
**instruction at the end**, and emits a plausible fake reply. On the organizer's
review turn it emits a MAD-style JSON verdict so convergence can be tested.
Streams line by line so you can see it "type" in a tmux pane.
"""
import sys
import time
import random

prompt = sys.stdin.read()
tail = prompt[-300:]  # only the trailing instruction, so prior document text won't fool us

lines: list[str] = []

if "one more round is needed" in tail:              # organizer review / verdict
    lines.append("[mock] Summary: broad agreement on a token bucket + per-key quota; "
                 "burst handling and error feedback still contested.")
    reached = "Yes" if "round 2/" in prompt or random.random() < 0.4 else "No"
    lines.append('{"consensus_reached": "%s", "reason": "core design is clear", '
                 '"current_answer": "token bucket + per-key quota + 429/Retry-After"}' % reached)
elif "report body" in tail:                          # organizer final report
    lines.append("### 概述")
    lines.append("[mock] Token bucket baseline + per-key quota, agreed across the board.")
    lines.append("### 各决策点结论")
    lines.append("- A: token bucket + per-key quota + 429/Retry-After.")
    lines.append("### 最终可执行建议")
    lines.append("- Return quota/reset in response headers.")
elif "kick off the discussion" in tail:              # organizer opening
    lines.append("[mock] Opening: three decision points — algorithm choice, quota dimension, over-limit feedback.")
    lines.append("Please weigh in on trade-offs, abuse protection, and developer experience.")
else:                                                # a debater's turn
    persona = "[mock]"
    for kw, tag in (("systems engineer", "alice"), ("security", "bob"), ("developer experience", "carol")):
        if kw in prompt:
            persona = f"[mock·{tag}]"
            break
    lines.append(f"{persona} I'd start from a simple, operable token bucket, limit per key,")
    lines.append("and put quota + reset time in response headers so callers can self-adapt.")

for ln in lines:
    sys.stdout.write(ln + "\n")
    sys.stdout.flush()
    time.sleep(0.3)
