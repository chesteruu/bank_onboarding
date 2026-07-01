from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ComponentInternalStep(BaseModel):
    key: str
    title: str | None = None
    integrations: list[str] = Field(default_factory=list)
    optional: bool = False
    form_schema: str | None = None


class ComponentFlowDefinition(BaseModel):
    component_id: str
    orchestrator: str
    internal_steps: list[ComponentInternalStep]

    def step_keys(self) -> list[str]:
        return [s.key for s in self.internal_steps]

    def get_step(self, key: str) -> ComponentInternalStep | None:
        return next((s for s in self.internal_steps if s.key == key), None)

    def next_step_key(self, current: str) -> str | None:
        keys = self.step_keys()
        try:
            idx = keys.index(current)
        except ValueError:
            return None
        if idx + 1 < len(keys):
            return keys[idx + 1]
        return None


class ComponentFlowProvider:
    def __init__(self, flows_dir: Path) -> None:
        self._flows_dir = flows_dir
        self._cache: dict[str, ComponentFlowDefinition] = {}

    def load(self, relative_path: str) -> ComponentFlowDefinition:
        if relative_path in self._cache:
            return self._cache[relative_path]
        path = self._flows_dir / relative_path
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        flow = ComponentFlowDefinition.model_validate(data)
        self._cache[relative_path] = flow
        return flow
