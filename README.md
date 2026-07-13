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
- **组织者 = MAD 的 moderator**：开场拆题 → 每轮结束输出一段小结 + 一行 JSON 裁决
  `{"consensus_reached": "Yes/No", "reason": ..., "current_answer": ...}` → `Yes` 就收敛结束。
- **人类随时插话**：直接编辑 `DISCUSSION.md`，或加 `--interactive` 让每轮结束时停下等你输入。
- **可靠**：纯文件读写 + 非交互 CLI（`claude -p` / `codex exec`），不抓 TUI 屏幕，没有 ready-detection 的坑。

## 快速开始

```bash
pip install -r requirements.txt          # 只依赖 PyYAML

# 1) 零成本冒烟测试（假 CLI，不花 token）
python3 run.py --config config.mock.yaml
tmux attach -t agent-debate-cli-mock         # 另开终端围观

# 2) 真跑（本机需装好 codex + claude 并登录）
python3 run.py                            # 用 config.example.yaml
tmux attach -t agent-debate-cli

# 每轮结束停下让你插话
python3 run.py --interactive
```

讨论产物就是仓库根目录的 `DISCUSSION.md`；每个 agent 的原始输出流另存于 `logs/<时间戳>/`。

## 配置（`config.example.yaml`）

```yaml
topic: "讨论的议题"
language: "中文"
max_rounds: 3               # 最多几轮；组织者裁决 Yes 会提前收敛
turn_word_limit: 200
document: "DISCUSSION.md"    # 共享文档路径
session: "agent-debate-cli"     # tmux 会话名

drivers:                     # 怎么以非交互方式调用某个 CLI
  claude: { cmd: ["claude", "-p"],        mode: stdin }
  codex:  { cmd: ["codex", "exec", "--"], mode: stdin }
  # mode: stdin -> prompt 走标准输入；mode: arg -> 作为末尾参数（用 {prompt} 占位）

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

## 适配你本机的 CLI

`drivers.cmd` 要能"给一段文字、返回一段文字"。上真跑前先手动验一下非交互模式：

```bash
echo "用一句话介绍你自己" | claude -p
echo "用一句话介绍你自己" | codex exec --
```

能返回文本就能接。不同版本参数可能不同，按实际改 `cmd`。

## 目录结构

```
run.py                 入口：装配 tmux 观众席 + 启动编排
config.example.yaml    真实 CLI 配置
config.mock.yaml       零成本测试配置
requirements.txt
src/
  config.py            读取/校验 YAML
  drivers.py           调用 CLI，流式写日志，返回文本
  document.py          SharedDoc：共享文档的初始化/读全文/序号/追加
  prompts.py           开场/发言/小结(JSON裁决)/收尾模板
  agent.py             角色 + 驱动 + 日志
  orchestrator.py      组织者主持的多轮主循环 + 人类插话
tools/
  mock_cli.py          假 CLI，供冒烟测试
DISCUSSION.md          每次运行生成的共享讨论文档（最终产物）
logs/<时间戳>/         每个 agent 的原始输出流
```

## 已知取舍

- **成本**：真跑每轮都把整份文档发给每个 agent，token 随轮数、人数、文档长度增长。
  用 `max_rounds`、`turn_word_limit` 控规模，先 mock 跑通再上真 CLI。
- **无会话记忆**：刻意用非交互模式，agent 不保留自己的历史——上下文全在共享文档里，更可控、可审计。
- **收敛靠 JSON 裁决**：组织者用 `consensus_reached` 字段决定结束，解析带容错（解析失败默认继续）。
  某个 CLI 不爱输出 JSON 时，可在 `prompts.py` 里加强约束，或靠 `max_rounds` 兜底。
- **串行发言**：按"圆桌"直觉一个接一个，便于观看与写文档；要并行需自行改造。
