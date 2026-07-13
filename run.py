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
import re
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.orchestrator import Orchestrator
from src import tmuxio


def slugify(topic: str, maxlen: int = 40) -> str:
    """把 topic 变成安全的文件夹名：去掉文件系统非法字符，空白转连字符，
    保留中英文，截断到 maxlen。"""
    s = topic.strip()
    s = re.sub(r'[\\/:*?"<>|]', "", s)      # 去掉文件系统非法字符
    s = re.sub(r"\s+", "-", s)               # 空白 -> 连字符
    s = s.strip("-.")
    s = s[:maxlen].strip("-.")
    return s or "discussion"


def main() -> int:
    ap = argparse.ArgumentParser(description="共享 md 文档 · 多 agent 圆桌讨论")
    ap.add_argument("--config", default="config.example.yaml")
    ap.add_argument("--interactive", action="store_true", help="每轮结束后暂停让人类插话")
    ap.add_argument("--no-tmux", action="store_true", help="不启动 tmux 观众席")
    ap.add_argument("--resume", metavar="DISCUSSION.md",
                    help="从一份已存在的 DISCUSSION.md 续跑（不清空、只在完整轮界继续）")
    args = ap.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)  # 让 driver 里的相对命令（如 tools/mock_cli.py）可用

    cfg = Config.load(args.config)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    reset = True
    if args.resume:
        # 续跑：文档=指定文件，日志写同目录，绝不清空
        cfg.document = os.path.abspath(args.resume)
        if not os.path.exists(cfg.document):
            print(f"  ✗ 找不到要续跑的文档：{cfg.document}")
            return 1
        log_dir = os.path.dirname(cfg.document)
        reset = False
    elif cfg.document:
        # 固定输出模式（config 里显式写了 document）：文档用该路径，日志放 logs/<时间戳>/
        log_dir = os.path.join(root, "logs", run_id)
    else:
        # 按 topic 自动分文件夹：discussions/<topic>/<时间戳>/{DISCUSSION.md, *.log}
        run_dir = os.path.join(root, cfg.output_dir, slugify(cfg.topic), run_id)
        cfg.document = os.path.join(run_dir, "DISCUSSION.md")
        log_dir = run_dir
    os.makedirs(log_dir, exist_ok=True)

    # 把本次运行用到的 config 快照进结果文件夹，方便复现（续跑不覆盖已有快照）
    try:
        snap = os.path.join(log_dir, os.path.basename(args.config))
        if not (args.resume and os.path.exists(snap)):
            shutil.copy(args.config, snap)
    except OSError:
        pass

    try:
        orch = Orchestrator(cfg, log_dir, interactive=args.interactive, reset=reset)
    except ValueError as e:
        print(f"  ✗ {e}")
        return 1

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

    try:
        doc_path = orch.run()
    except ValueError as e:
        print(f"  ✗ {e}")
        return 1

    print(f"\n  ✅ 讨论结束。完整记录：{os.path.abspath(doc_path)}")
    if wall:
        print(f"  （tmux 会话 {cfg.session} 仍在，看完可 tmux kill-session -t {cfg.session}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
