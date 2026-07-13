#!/usr/bin/env python3
"""假 CLI，用来零成本测试编排流程（不消耗任何 token）。

从 stdin 读 prompt，按**结尾指令**判断这是哪种发言，吐出合理的假回复。
组织者小结时会输出 MAD 风格的 JSON 裁决，方便测试收敛判定。逐行带延迟输出，
方便在 tmux pane 里看流式效果。
"""
import sys
import time
import random

prompt = sys.stdin.read()
tail = prompt[-300:]  # 只看结尾指令，避免被前文文档干扰

lines: list[str] = []

if "还需再讨论一轮" in tail:                       # 组织者·小结/裁决
    lines.append("[mock] 小结：各方在令牌桶+按 key 配额上趋于一致，尚存 burst 与错误反馈的细节分歧。")
    reached = "Yes" if "第 2" in prompt or random.random() < 0.4 else "No"
    lines.append('{"consensus_reached": "%s", "reason": "核心方案已清晰", "current_answer": "令牌桶+按key配额+429/Retry-After"}' % reached)
elif "最终产出" in tail:                            # 组织者·最终结论
    lines.append("[mock] 最终结论：采用令牌桶做基础限流，按 API key 维度配额，")
    lines.append("对突发流量保留 burst 余量，超限返回 429 并带 Retry-After 与剩余额度响应头。")
elif "请你开场" in tail:                            # 组织者·开场
    lines.append("[mock] 开场：分三点讨论——算法选型、配额维度、超限反馈。")
    lines.append("请各位重点谈方案取舍、滥用防护与开发者体验。")
else:                                               # 讨论者发言
    persona = "[mock]"
    for kw, tag in (("系统工程师", "alice"), ("安全", "bob"), ("开发者体验", "carol")):
        if kw in prompt:
            persona = f"[mock·{tag}]"
            break
    lines.append(f"{persona} 我倾向从简单可运维的令牌桶起步，按 key 维度限流，")
    lines.append("并把额度与重置时间写进响应头，方便调用方自适应。")

for ln in lines:
    sys.stdout.write(ln + "\n")
    sys.stdout.flush()
    time.sleep(0.3)
