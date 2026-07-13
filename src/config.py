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
    max_rounds: int
    turn_word_limit: int
    per_turn_timeout: int
    document: str
    session: str
    drivers: dict[str, DriverSpec]
    organizer: AgentSpec
    agents: list[AgentSpec] = field(default_factory=list)

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

        cfg = Config(
            topic=raw["topic"],
            language=raw.get("language", "中文"),
            max_rounds=int(raw.get("max_rounds", 3)),
            turn_word_limit=int(raw.get("turn_word_limit", 200)),
            per_turn_timeout=int(raw.get("per_turn_timeout", 300)),
            document=raw.get("document", "DISCUSSION.md"),
            session=raw.get("session", "agent-debate-cli"),
            drivers=drivers,
            organizer=mk_agent(raw["organizer"]),
            agents=[mk_agent(a) for a in raw["agents"]],
        )
        if not cfg.agents:
            raise ValueError("至少需要配置一个讨论者（agents）")
        return cfg
