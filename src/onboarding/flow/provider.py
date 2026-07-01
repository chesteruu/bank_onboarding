from pathlib import Path

import yaml
from pydantic import TypeAdapter

from onboarding.domain.enums import AccountType, Country
from onboarding.domain.models import FlowDefinition


class YamlFlowDefinitionProvider:
    def __init__(self, flows_dir: Path) -> None:
        self._flows_dir = flows_dir
        self._cache: dict[tuple[Country, AccountType], FlowDefinition] = {}
        self._by_id: dict[str, FlowDefinition] = {}
        self._adapter = TypeAdapter(FlowDefinition)

    def _load_file(self, path: Path) -> FlowDefinition:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return self._adapter.validate_python(data)

    def _ensure_loaded(self) -> None:
        if self._by_id:
            return
        for path in sorted(self._flows_dir.glob("*.yaml")):
            flow = self._load_file(path)
            self._by_id[flow.flow_id] = flow
            if flow.country is not None and flow.account_type is not None:
                self._cache[(flow.country, flow.account_type)] = flow

    def get_flow(self, country: Country, account_type: AccountType) -> FlowDefinition:
        self._ensure_loaded()
        key = (country, account_type)
        if key not in self._cache:
            raise KeyError(f"No flow defined for {country.value}/{account_type.value}")
        return self._cache[key]

    def get_flow_by_id(self, flow_id: str) -> FlowDefinition:
        self._ensure_loaded()
        if flow_id not in self._by_id:
            raise KeyError(f"No flow defined with id {flow_id}")
        return self._by_id[flow_id]

    def list_flows(self) -> list[FlowDefinition]:
        self._ensure_loaded()
        return list(self._by_id.values())
