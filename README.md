# agent-debate-cli

> Let your local CLI agents (Claude Code, Codex, …) **debate a topic in a shared Markdown document**.
> Moderator-led, MAD-style multi-agent debate, with a live tmux view. No API keys of your own — it drives the CLIs you already use.

**Topics（发布到 GitHub 时填这些，利于搜索）**：`multi-agent-debate` · `llm-debate` · `agent` · `claude-code` · `codex` · `tmux` · `cli` · `markdown`

---

让本地的多个 CLI agent（codex、claude code……）**围绕一份共享 Markdown 文档**开圆桌讨论：
一个**组织者**主持，若干**讨论者**按角色轮流在文档末尾追加署名发言，组织者每轮裁决是否收敛，
最后给出结论。整场讨论就是一份可 git、可人肉编辑的 `DISCUSSION.md`。

结构借鉴多智能体辩论框架 [MAD (Multi-Agents-Debate)](https://github.com/Skytliang/Multi-Agents-Debate)：
`moderator + players + 多轮 + JSON 裁决`，但把 MAD 的"记忆广播"换成了**共享文档广播**，
并用你本机真实的 CLI 来驱动每个 agent。

```
        DISCUSSION.md  ← 唯一真相源 / 广播总线 / 最终产物
   ┌─────────┬─────────┬─────────┐
   │  chair  │  alice  │   bob   │  ...每个 agent 一个 tmux pane
   │ 组织者   │ (codex) │(claude) │     实时看它们往文档里写
   └─────────┴─────────┴─────────┘
```

## 它怎么工作

CLI 每次调用是**无状态**的，所以每一轮编排器都把 `DISCUSSION.md` 的**当前全文**塞进 prompt，
再让下一个 agent 发言。于是：

- **共享文档 = 广播总线**：每个 agent 读全文 → 追加自己的发言 → 下一位读到（含你的手动编辑）。
- **组织者 = MAD 的 moderator**：开场拆题 → 每轮结束输出小结 + **最后一行** JSON 裁决
  `{"consensus_reached": "Yes/No", "reason": ..., "current_answer": ...}` → `Yes` 且本轮无失败才收敛。
- **人类随时插话**：直接编辑 `DISCUSSION.md`，或加 `--interactive` 让每轮结束时停下等你输入。
- **可靠**：纯文件读写 + 非交互 CLI，不抓 TUI 屏幕；CLI 调用有超时+进程组 kill、失败被记为失败记录而非当作发言、文档做防伪造清洗（见「可靠性」）。

## 快速开始

```bash
pip install -r requirements.txt          # 运行只依赖 PyYAML

# 1) 零成本冒烟测试（假 CLI，不花 token）
python3 run.py --config config.mock.yaml
tmux attach -t agent-debate-cli-mock         # 另开终端围观

# 2) 真跑（本机需装好 codex + claude 并登录）
python3 run.py                            # 用 config.example.yaml
tmux attach -t agent-debate-cli

# 每轮结束停下让你插话
python3 run.py --interactive

# 跑测试
pip install -r requirements-dev.txt && python3 -m pytest
```

每次运行按议题分文件夹存到 `discussions/<topic>/<时间戳>/`，里面有：讨论全文 `DISCUSSION.md`、
各 agent 原始输出流 `<name>.log`、以及**本次用的 config 快照**（复现用）。`discussions/` 已在 `.gitignore`。

## 配置（`config.example.yaml`）

```yaml
topic: "讨论的议题"
language: "English"          # 辩论语言
report_language: "中文"       # 组织者最终报告的语言（不填则同 language）
max_rounds: 3               # 最多几轮；组织者裁决 Yes 且本轮无失败会提前收敛
turn_word_limit: 200
output_dir: "discussions"    # 按 topic 自动分文件夹的根目录（留空 document 即用此模式）
session: "agent-debate-cli"  # tmux 会话名

drivers:                     # 怎么以非交互方式调用某个 CLI
  claude: { cmd: ["claude", "-p", "--output-format", "text"], mode: stdin }
  codex:  { cmd: ["codex", "exec", "--output-last-message", "{outfile}", "-"], mode: stdin }
  # mode: stdin -> prompt 走标准输入；mode: arg -> 作为末尾参数（用 {prompt} 占位）
  # {outfile} -> 驱动读这个临时文件当"干净结果"，脏 stdout 只进日志（codex 的 banner/回显需要）

organizer:                   # 组织者 / 主持人
  name: chair
  driver: claude
  role: "你是圆桌讨论的组织者……"

agents:                      # 讨论者，数量随意，增删即可
  - { name: alice, driver: codex,  role: "偏好简单方案的系统工程师" }
  - { name: bob,   driver: claude, role: "关注安全与稳定性的评审" }
  - { name: carol, driver: codex,  role: "代表开发者体验" }
```

加人就往 `agents` 里加一项；换角色改 `role`；混用不同 CLI 改 `driver`。
仓库自带几个 config：`config.example.yaml`（通用）、`config.mock.yaml`（零成本测试）、
`config.design.yaml`（评审本 repo）、`config.plan.yaml`（把评审结论落成实施计划）。

## 适配你本机的 CLI

`drivers.cmd` 要能"给一段文字、返回一段文字"。上真跑前先手动验一下非交互模式：

```bash
echo "用一句话介绍你自己" | claude -p --output-format text
echo "用一句话介绍你自己" | codex exec -        # 末尾 - = 整个 prompt 从 stdin 读
```

能返回文本就能接。不同版本参数可能不同，按实际改 `cmd`。
（claude 若卡在权限询问，给它加 `--permission-mode dontAsk --allowedTools ""`，先 `claude --help` 核对取值。）

## 目录结构

```
run.py                 入口：分文件夹存盘 + 装配 tmux 观众席 + 启动编排
config.*.yaml          example / mock / design / plan 四套配置
requirements.txt       运行依赖（PyYAML）
requirements-dev.txt   测试依赖（pytest）
src/
  config.py            读取/校验 YAML
  drivers.py           调用 CLI，返回 DriverResult(text,status,error)；超时/进程组 kill/清洗
  document.py          SharedDoc：初始化/读全文/只认标题的序号/防伪造追加
  prompts.py           开场/发言/小结(JSON裁决)/最终报告 模板
  agent.py             角色 + 驱动 + 日志
  orchestrator.py      组织者主持的多轮主循环 + 失败不收敛 + 人类插话
tools/
  mock_cli.py          假 CLI，供冒烟测试
tests/
  test_pr1.py          驱动/裁决/文档完整性/收敛 的回归测试
discussions/<topic>/<时间戳>/   每次运行的产物（DISCUSSION.md + 各 .log + config 快照）
```

## 可靠性

- **调用超时真的会触发**：`drivers.py` 用 reader/writer 线程避免大 prompt 与 stdout 的管道死锁，
  单调 deadline == `per_turn_timeout`（总墙钟预算），到期 SIGTERM→等 grace→SIGKILL 杀整个进程组。
- **失败不当发言**：CLI 超时/非零退出会写成清晰的「失败记录」而非把报错/横幅当作发言；
  含失败轮次的这一轮永不判定收敛（`reached = 裁决Yes and 本轮无失败`）。
- **裁决稳**：`_parse_verdict` 只取**最后一非空行** `json.loads` 并校验 `consensus_reached ∈ {Yes,No}`，
  解析失败默认 No（宁可多一轮，不假收敛）。
- **文档不可伪造**：`append` 会转义正文里伪造的 `## [` 标题与 `· #N ·` 序号标记；`next_seq` 只认真标题行。

## 已知取舍

- **成本**：真跑每轮都把整份文档发给每个 agent，token 随轮数、人数、文档长度增长。
  用 `max_rounds`、`turn_word_limit` 控规模，先 mock 跑通再上真 CLI。（上下文封顶/摘要属后续 PR2。）
- **无会话记忆**：刻意用非交互模式，agent 不保留自己的历史——上下文全在共享文档里，更可控、可审计。
- **串行发言**：按"圆桌"直觉一个接一个，便于观看与写文档；要并行需自行改造。
- **非破坏/续跑**：目前每次启动会重建文档；`--resume` 与上下文体积告警是规划中的 PR2。
