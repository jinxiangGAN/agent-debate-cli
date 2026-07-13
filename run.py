#!/usr/bin/env python3
"""共享文档圆桌讨论 · 入口。

用法：
    python3 run.py                            # 用 config.example.yaml（真实 CLI）
    python3 run.py --config config.mock.yaml  # 零成本冒烟测试
    python3 run.py --interactive              # 每轮结束后停下，让你插话
    python3 run.py --no-tmux                  # 不开 tmux 观众席

跑起来后，另开一个终端：
    tmux attach -t <session>
最上面那个大 pane 就是 DISCUSSION.md 在实时生长；讨论全程也写在该文件里。
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.orchestrator import Orchestrator
from src import tmuxio


def main() -> int:
    ap = argparse.ArgumentParser(description="共享 md 文档 · 多 agent 圆桌讨论")
    ap.add_argument("--config", default="config.example.yaml")
    ap.add_argument("--interactive", action="store_true", help="每轮结束后暂停让人类插话")
    ap.add_argument("--no-tmux", action="store_true", help="不启动 tmux 观众席")
    args = ap.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)  # 让 driver 里的相对命令（如 tools/mock_cli.py）可用

    cfg = Config.load(args.config)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = os.path.join(root, "logs", run_id)
    os.makedirs(log_dir, exist_ok=True)

    orch = Orchestrator(cfg, log_dir, interactive=args.interactive)

    wall = None
    if not args.no_tmux and tmuxio.available():
        wall = tmuxio.TmuxWall(cfg.session)
        for title, path in orch.agent_log_paths():
            wall.add_pane(title, path)
        print(f"\n  tmux 观众席已就绪。另开终端运行：\n    tmux attach -t {cfg.session}\n")
    elif not args.no_tmux:
        print("  ⚠️ 未找到 tmux，跳过可视化（讨论仍会进行）。")

    print(f"  议题：{cfg.topic}")
    print(f"  组织者：{cfg.organizer.name}  讨论者：{', '.join(a.name for a in cfg.agents)}")
    print(f"  共享文档：{os.path.abspath(cfg.document)}")
    print(f"  日志目录：{log_dir}\n  讨论进行中……\n")

    doc_path = orch.run()

    print(f"\n  ✅ 讨论结束。完整记录：{os.path.abspath(doc_path)}")
    if wall:
        print(f"  （tmux 会话 {cfg.session} 仍在，看完可 tmux kill-session -t {cfg.session}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
