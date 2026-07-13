# agent-debate-cli

**Make your local CLI agents debate.** Point Claude Code, Codex (any non-interactive CLI) at a
question; a moderator opens it, the agents argue in turns over one shared Markdown document, and you
get an auditable transcript plus a final report. No API keys of your own — it drives the CLIs you
already have logged in.

Structure borrowed from [MAD (Multi-Agents-Debate)](https://github.com/Skytliang/Multi-Agents-Debate)
— `moderator + players + rounds + JSON verdict` — but the "memory broadcast" is a shared file every
agent reads and appends to, and the players are your real local CLIs.

<details>
<summary><b>What a run produces</b> (excerpt of a real <code>DISCUSSION.md</code>)</summary>

```markdown
# Roundtable debate: How should we design rate limiting for a public API?

## [chair] Organizer · Opening · #1 · 2026-07-13 23:13
Three decision points — algorithm choice, quota dimension, over-limit feedback.
Please weigh in on trade-offs, abuse protection, and developer experience.

## [alice] Round 1 · #2 · 2026-07-13 23:13
I'd start from a simple, operable token bucket, limit per key, and put quota +
reset time in response headers so callers can self-adapt.

## [chair] Organizer · Round 1 summary · #5 · 2026-07-13 23:13
Broad agreement on a token bucket + per-key quota; burst handling still contested.
{"consensus_reached": "No", "reason": "core design is clear", "current_answer": "token bucket + per-key quota + 429/Retry-After"}

## [chair] Organizer · Final report · #10 · 2026-07-13 23:13
Use a token bucket for baseline limiting, quota per API key, keep burst headroom,
return 429 with Retry-After and remaining-quota headers.
```
</details>

## Prerequisites

- **Python ≥ 3.10** (runtime dep: PyYAML only).
- **The CLIs you want to debate**, installed and logged in — e.g.
  `npm i -g @anthropic-ai/claude-code` and `npm i -g @openai/codex`. Verify each returns text
  non-interactively:
  ```bash
  echo "introduce yourself in one line" | claude -p --output-format text
  echo "introduce yourself in one line" | codex exec -
  ```
- **tmux ≥ 3.0** *(optional)* — only for the live pane view; everything runs fine without it.

## Quickstart (5 minutes, mock-first — spends no tokens)

```bash
pip install -r requirements.txt

# 1) Dry run with a fake CLI — proves the whole pipeline without any token cost
python3 run.py --config configs/mock.yaml
#    watch it live in another terminal (optional):
tmux attach -t agent-debate-cli-mock

# 2) The real thing (needs claude + codex installed & logged in)
python3 run.py --config configs/example.yaml
tmux attach -t agent-debate-cli
```

Every run is saved to `discussions/<topic>/<timestamp>/`: the transcript `DISCUSSION.md`, each
agent's raw stream `<name>.log`, and a **snapshot of the config used** (for reproducibility).

Other flags: `--interactive` (pause each round so you can add a `## [You]` note),
`--no-tmux`, and `--resume <DISCUSSION.md>` (continue a crashed/interrupted run from the last
complete round). Exit codes: `0` converged, `2` ran out of rounds without consensus, `1` error.

## Configure it

Everything is YAML — roles, how many agents, which CLI plays whom, the topic. No code changes.

```yaml
topic: "The question to debate"
language: "English"          # language of the debate
report_language: "中文"       # language of the organizer's final report (defaults to language)
max_rounds: 3                # ends early once the organizer verdict is Yes and the round had no failure
turn_word_limit: 200
output_dir: "discussions"    # leave `document` empty to auto-organize per topic under here
session: "agent-debate-cli"  # tmux session name

drivers:                     # how to call each CLI non-interactively
  claude: { cmd: ["claude", "-p", "--output-format", "text"], mode: stdin }
  codex:  { cmd: ["codex", "exec", "--output-last-message", "{outfile}", "-"], mode: stdin }

organizer:                   # the moderator
  name: chair
  driver: claude
  role: "You are the chair of the roundtable…"

agents:                      # debaters — add/remove freely, any number
  - { name: alice, driver: codex,  role: "A systems engineer who favors simple solutions" }
  - { name: bob,   driver: claude, role: "A security & reliability reviewer" }
```

| Key | Meaning |
| --- | --- |
| `topic` | the question to debate (required) |
| `language` / `report_language` | debate language / final-report language (report defaults to `language`) |
| `max_rounds` | max debate rounds; converges earlier on a Yes verdict |
| `turn_word_limit` | word cap per contribution |
| `per_turn_timeout` | seconds before a stuck CLI call is killed (default 300) |
| `context_warn_chars` | warn (read-only) when the doc sent to a prompt exceeds this (default 200000) |
| `document` | fixed output path; **leave empty** to auto-organize under `output_dir` |
| `output_dir` | root for auto per-topic folders (default `discussions`) |
| `session` | tmux session name |
| `context` / `context_file` | optional background text / a file (resolved **relative to the config file**) seeded into the doc |
| `drivers.<name>.cmd` | argv; `{prompt}` (arg mode) and `{outfile}` (clean-output file) are substituted |
| `drivers.<name>.mode` | `stdin` (prompt piped in) or `arg` (prompt appended / `{prompt}`) |
| `organizer`, `agents[]` | `{name, driver, role}`; `driver` must be a defined driver; names unique |

Bundled configs: `configs/example.yaml` (general), `configs/mock.yaml` (zero-cost test),
`configs/design.yaml` (review this repo), `configs/plan.yaml` (turn a review into a plan),
`configs/review2.yaml` (maturity/generalization review).

Malformed configs fail fast with a field-path message (e.g. `config error: drivers.codex.mode
must be 'arg' or 'stdin'`) before any agent is launched.

## How it works

Each CLI call is **stateless**, so every round the orchestrator packs the *current full document*
into the prompt and lets the next agent speak. The shared `DISCUSSION.md` is the broadcast bus, the
audit trail, and the final artifact all at once — and you can edit it by hand between turns.

## Reliability

- **Timeouts actually fire.** Reader/writer threads avoid a large-prompt↔stdout pipe deadlock; a
  single monotonic deadline (`per_turn_timeout`) escalates SIGTERM → grace → SIGKILL on the whole
  process group.
- **Failures aren't published as speech.** A timed-out / non-zero CLI becomes a labelled *failure
  record*; a round containing a failure can never be declared converged.
- **Verdicts are robust and observable.** The organizer's last non-empty line must be
  `{"consensus_reached": "Yes"|"No", …}`; a parse failure is logged to stderr and treated as No
  (so a prompt drift can't silently burn every round).
- **The document can't be forged.** `append` escapes body lines that mimic `## [` headings or the
  `· #N ·` sequence marker; `next_seq` reads real heading lines only.
- **Resumable, non-destructive.** `--resume` continues from the last complete round; it refuses on a
  topic mismatch and skips an already-finished doc.

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest
```

`tests/` covers driver timeout/kill, outfile handling, verdict parsing, document anti-forgery,
failure-blocks-convergence, `--resume`, the size warning, and config validation.

## Project layout

```
run.py                 entry point (folder-per-run, tmux wall, orchestration)
configs/               example / mock / design / plan / review2 YAML configs
src/
  config.py            YAML load + validation
  drivers.py           CLI invocation -> DriverResult(text,status,error); timeout / process-group kill
  document.py          SharedDoc: init / read / heading-only next_seq / anti-forgery append / resume introspection
  prompts.py           opening / turn / review(JSON verdict) / final-report templates
  agent.py             role + driver + log
  orchestrator.py      moderator-led rounds, failure-aware convergence, human turns
tools/mock_cli.py      fake CLI for the zero-cost smoke test
tests/                 pytest suite
```

## Known trade-offs

- **Cost** grows with rounds × agents × document length (the full doc is re-sent each round). Keep
  `max_rounds` / `turn_word_limit` modest; a size warning fires past `context_warn_chars`. True
  context capping / summarization is intentionally deferred.
- **No per-agent memory** — context lives entirely in the shared doc (auditable, controllable).
- **Serial turns** by design (easy to watch and to write the doc); parallelism would need work.
- **POSIX process-group kill** — `_kill()` uses `os.killpg`/`SIGKILL`; Windows support is deferred.

---

<details>
<summary>中文简介</summary>

让本地的多个 CLI agent（Claude Code、Codex……）**围绕一份共享 Markdown 文档**开圆桌辩论：
组织者开场 → 讨论者按角色轮流在文末追加署名发言 → 组织者每轮用一行 JSON 裁决是否收敛 →
产出一份中文/英文最终报告。整场讨论就是一份可 git、可人肉编辑的 `DISCUSSION.md`。

上手：`pip install -r requirements.txt` → `python3 run.py --config configs/mock.yaml`（零成本试跑）→
装好并登录 `claude`/`codex` 后 `python3 run.py --config configs/example.yaml`。每次运行存到
`discussions/<议题>/<时间戳>/`（含讨论全文、各 agent 日志、config 快照）。角色/数量/驱动/议题全在 YAML 里改，不动代码。

可靠性、`--resume`、退出码等细节见上面的英文章节。
</details>

## License

MIT — see [LICENSE](LICENSE).
