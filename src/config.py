"""加载并校验 YAML 配置。

校验层给的是**带字段路径的可操作报错**（ConfigError），而不是把畸形 YAML 直接
抛成 Python 的 KeyError/TypeError——在启动昂贵的 agent 之前就把配置问题讲清楚。
"""
from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field


class ConfigError(ValueError):
    """配置错误，消息里带字段路径。"""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(f"config error: {msg}")


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
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError:
            raise ConfigError(f"config error: file not found: {path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"config error: invalid YAML in {path}: {e}")
        _require(isinstance(raw, dict), f"{path}: top level must be a mapping")

        # ---- required top-level keys ----
        for key in ("topic", "drivers", "organizer", "agents"):
            _require(key in raw, f"missing required key: '{key}'")
        _require(isinstance(raw["topic"], str) and raw["topic"].strip(),
                 "'topic' must be a non-empty string")

        # ---- numeric fields (positive ints) ----
        def _pos_int(key: str, default: int) -> int:
            v = raw.get(key, default)
            _require(isinstance(v, int) and not isinstance(v, bool) and v > 0,
                     f"'{key}' must be a positive integer (got {v!r})")
            return v

        max_rounds = _pos_int("max_rounds", 3)
        turn_word_limit = _pos_int("turn_word_limit", 200)
        per_turn_timeout = _pos_int("per_turn_timeout", 300)
        context_warn_chars = _pos_int("context_warn_chars", 200_000)

        # ---- drivers ----
        _require(isinstance(raw["drivers"], dict) and raw["drivers"],
                 "'drivers' must be a non-empty mapping")
        drivers: dict[str, DriverSpec] = {}
        for name, d in raw["drivers"].items():
            fp = f"drivers.{name}"
            _require(isinstance(d, dict), f"{fp} must be a mapping")
            _require(isinstance(d.get("cmd"), list) and len(d["cmd"]) > 0,
                     f"{fp}.cmd must be a non-empty list")
            _require(all(isinstance(c, str) for c in d["cmd"]),
                     f"{fp}.cmd must be a list of strings")
            mode = d.get("mode", "arg")
            _require(mode in ("arg", "stdin"), f"{fp}.mode must be 'arg' or 'stdin' (got {mode!r})")
            drivers[name] = DriverSpec(name=name, cmd=list(d["cmd"]), mode=mode)

        # ---- agents / organizer ----
        seen: set[str] = set()

        def mk_agent(a: dict, fp: str) -> AgentSpec:
            _require(isinstance(a, dict), f"{fp} must be a mapping")
            for k in ("name", "driver", "role"):
                _require(k in a and isinstance(a[k], str) and a[k].strip(),
                         f"{fp}.{k} must be a non-empty string")
            _require(a["driver"] in drivers,
                     f"{fp}.driver '{a['driver']}' is not defined in 'drivers'")
            _require(a["name"] not in seen, f"duplicate participant name: '{a['name']}'")
            seen.add(a["name"])
            return AgentSpec(name=a["name"], driver=a["driver"], role=a["role"].strip())

        organizer = mk_agent(raw["organizer"], "organizer")
        _require(isinstance(raw["agents"], list) and len(raw["agents"]) >= 1,
                 "'agents' must be a non-empty list (at least one debater)")
        agents = [mk_agent(a, f"agents[{i}]") for i, a in enumerate(raw["agents"])]

        # ---- context / context_file (resolved relative to the CONFIG file's dir) ----
        context = raw.get("context", "") or ""
        cf = raw.get("context_file")
        if cf:
            _require(isinstance(cf, str), "context_file must be a string path")
            cf_path = cf if os.path.isabs(cf) else os.path.join(os.path.dirname(os.path.abspath(path)), cf)
            _require(os.path.isfile(cf_path), f"context_file not found/readable: {cf} (looked at {cf_path})")
            with open(cf_path, "r", encoding="utf-8") as f:
                context = (context + "\n\n" + f.read()).strip()

        language = raw.get("language", "中文")
        return Config(
            topic=raw["topic"],
            language=language,
            report_language=raw.get("report_language", "") or language,
            max_rounds=max_rounds,
            turn_word_limit=turn_word_limit,
            per_turn_timeout=per_turn_timeout,
            context_warn_chars=context_warn_chars,
            document=raw.get("document", "") or "",
            output_dir=raw.get("output_dir", "discussions"),
            session=raw.get("session", "agent-debate-cli"),
            drivers=drivers,
            organizer=organizer,
            agents=agents,
            context=context,
        )
