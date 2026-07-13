"""加载并校验 YAML 配置。"""
from __future__ import annotations
import yaml
from dataclasses import dataclass, field


@dataclass
class DriverSpec:
    name: str
    cmd: list[str]
    mode: str = "arg"  # "arg" | "stdin"


@dataclass
class AgentSpec:
    name: str
    driver: str
    role: str


@dataclass
class Config:
    topic: str
    language: str
    report_language: str   # language of the manager's final report (defaults to `language`)
    max_rounds: int
    turn_word_limit: int
    per_turn_timeout: int
    context_warn_chars: int   # warn (read-only) when the doc fed to a prompt exceeds this
    document: str          # 固定输出路径；留空则按 topic 自动分文件夹
    output_dir: str        # 自动模式下的根目录（discussions/<topic>/<时间戳>/）
    session: str
    drivers: dict[str, DriverSpec]
    organizer: AgentSpec
    agents: list[AgentSpec] = field(default_factory=list)
    context: str = ""  # 可选背景资料，讨论开始前写进文档供所有 agent 阅读

    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        drivers = {
            name: DriverSpec(name=name, cmd=list(d["cmd"]), mode=d.get("mode", "arg"))
            for name, d in raw["drivers"].items()
        }

        def mk_agent(a: dict) -> AgentSpec:
            spec = AgentSpec(name=a["name"], driver=a["driver"], role=a["role"].strip())
            if spec.driver not in drivers:
                raise ValueError(f"agent '{spec.name}' 引用了未定义的 driver '{spec.driver}'")
            return spec

        # 背景资料：可内联 context，也可用 context_file 指向一个文件（如 README.md）
        context = raw.get("context", "") or ""
        if raw.get("context_file"):
            import os as _os
            cf = raw["context_file"]
            if _os.path.exists(cf):
                with open(cf, "r", encoding="utf-8") as _f:
                    context = (context + "\n\n" + _f.read()).strip()

        language = raw.get("language", "中文")
        cfg = Config(
            topic=raw["topic"],
            language=language,
            report_language=raw.get("report_language", "") or language,
            max_rounds=int(raw.get("max_rounds", 3)),
            turn_word_limit=int(raw.get("turn_word_limit", 200)),
            per_turn_timeout=int(raw.get("per_turn_timeout", 300)),
            context_warn_chars=int(raw.get("context_warn_chars", 200_000)),
            document=raw.get("document", "") or "",
            output_dir=raw.get("output_dir", "discussions"),
            session=raw.get("session", "agent-debate-cli"),
            drivers=drivers,
            organizer=mk_agent(raw["organizer"]),
            agents=[mk_agent(a) for a in raw["agents"]],
            context=context,
        )
        if not cfg.agents:
            raise ValueError("至少需要配置一个讨论者（agents）")
        return cfg
