"""Agent = 一个角色 + 一个驱动 + 一个日志文件。"""
from __future__ import annotations
import os
from .config import AgentSpec
from .drivers import Driver


class Agent:
    def __init__(self, spec: AgentSpec, driver: Driver, log_dir: str):
        self.spec = spec
        self.driver = driver
        self.log_path = os.path.join(log_dir, f"{spec.name}.log")
        open(self.log_path, "w", encoding="utf-8").close()

    @property
    def name(self) -> str:
        return self.spec.name

    def run(self, header: str, prompt: str, timeout: int) -> str:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\033[1;36m▶ {header}\033[0m\n")
        return self.driver.invoke(prompt, self.log_path, timeout)
