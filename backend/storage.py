"""Atomic local JSON repositories."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import List
from uuid import uuid4

from backend.errors import ConflictError, NotFoundError
from backend.models import (
    AccountConfig,
    LyricTemplateConfig,
    PipelineSnapshot,
    PipelineQueueSnapshot,
    SongRecord,
    MonitoringSnapshot,
)


class JsonStore:
    def __init__(self, path: Path, default: Any) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.default = default
        self._value = self._load()

    def read(self) -> Any:
        return self._value

    def write(self, value: Any) -> None:
        destination = self.path
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        payload = _json_dump(value)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        self._value = value

    def _load(self) -> Any:
        if not self.path.exists():
            return self.default
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                import json

                return json.load(handle)
        except (OSError, ValueError, TypeError):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = self.path.with_name(f"{self.path.stem}.{stamp}.corrupt{self.path.suffix}")
            self.path.replace(backup)
            return self.default


def _json_dump(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


class AccountRepository:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, default=[])

    def list(self) -> list[AccountConfig]:
        return [AccountConfig.model_validate(item) for item in self._store.read()]

    def get(self, account_id: str) -> AccountConfig:
        for account in self.list():
            if account.id == account_id:
                return account
        raise NotFoundError(f"账号不存在: {account_id}")

    def create(self, account: AccountConfig) -> AccountConfig:
        accounts = self.list()
        self._ensure_unique(account, accounts)
        accounts.append(account)
        self._persist(accounts)
        return account

    def update(self, account_id: str, account: AccountConfig) -> AccountConfig:
        accounts = self.list()
        self._ensure_unique(account, accounts, ignored_id=account_id)
        for index, current in enumerate(accounts):
            if current.id == account_id:
                updated = account.model_copy(update={"id": account_id})
                accounts[index] = updated
                self._persist(accounts)
                return updated
        raise NotFoundError(f"账号不存在: {account_id}")

    def copy(self, account_id: str, new_name: str) -> AccountConfig:
        source = self.get(account_id)
        copied = source.model_copy(
            update={
                "id": uuid4().hex,
                "account_name": new_name,
                "chrome_debug_port": self._next_port(),
            }
        )
        return self.create(copied)

    def delete(self, account_id: str) -> None:
        accounts = self.list()
        remaining = [account for account in accounts if account.id != account_id]
        if len(remaining) == len(accounts):
            raise NotFoundError(f"账号不存在: {account_id}")
        self._persist(remaining)

    def _next_port(self) -> int:
        ports = [account.chrome_debug_port for account in self.list()]
        return max(ports, default=9221) + 1

    def _ensure_unique(
        self,
        account: AccountConfig,
        accounts: List[AccountConfig],
        ignored_id: str | None = None,
    ) -> None:
        for current in accounts:
            if current.id == ignored_id:
                continue
            if current.account_name == account.account_name:
                raise ConflictError(f"账号名称已存在: {account.account_name}")
            if current.chrome_debug_port == account.chrome_debug_port:
                raise ConflictError(f"调试端口已被账号 {current.account_name} 使用: {account.chrome_debug_port}")

    def _persist(self, accounts: List[AccountConfig]) -> None:
        self._store.write([account.model_dump(mode="json") for account in accounts])


class RunStateRepository:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, default={"runs": {}})

    def get(self, day: str, account_name: str, file_name: str) -> SongRecord | None:
        record = self._runs().get(day, {}).get(account_name, {}).get(file_name)
        return SongRecord.model_validate(record) if record else None

    def list(self, day: str, account_name: str) -> list[SongRecord]:
        records = self._runs().get(day, {}).get(account_name, {})
        return [SongRecord.model_validate(records[name]) for name in sorted(records)]

    def mark(self, day: str, account_name: str, record: SongRecord) -> None:
        value = self._store.read()
        runs = value.setdefault("runs", {})
        runs.setdefault(day, {}).setdefault(account_name, {})[record.file_name] = record.model_dump(mode="json")
        self._store.write(value)

    def _runs(self) -> dict:
        value = self._store.read()
        return value.get("runs", {}) if isinstance(value, dict) else {}


class PipelineStateRepository:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, default=None)

    def get(self) -> PipelineSnapshot | None:
        value = self._store.read()
        return PipelineSnapshot.model_validate(value) if value else None

    def save(self, snapshot: PipelineSnapshot) -> None:
        self._store.write(snapshot.model_dump(mode="json"))


class PipelineQueueStateRepository:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, default=None)

    def get(self) -> PipelineQueueSnapshot | None:
        value = self._store.read()
        return PipelineQueueSnapshot.model_validate(value) if value else None

    def save(self, snapshot: PipelineQueueSnapshot) -> None:
        self._store.write(snapshot.model_dump(mode="json"))


class MonitoringRepository:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, default={"snapshots": []})

    def save(self, snapshot: MonitoringSnapshot) -> MonitoringSnapshot:
        value = self._value()
        snapshots = value.setdefault("snapshots", [])
        if not isinstance(snapshots, list):
            snapshots = []
            value["snapshots"] = snapshots
        snapshots.append(snapshot.model_dump(mode="json"))
        snapshots.sort(key=lambda item: str(item.get("collected_at") or ""), reverse=True)
        value["snapshots"] = snapshots
        self._store.write(value)
        return snapshot

    def list_snapshots(self, account_id: str | None = None) -> list[MonitoringSnapshot]:
        snapshots = [
            MonitoringSnapshot.model_validate(item)
            for item in self._value().get("snapshots", [])
            if isinstance(item, dict)
        ]
        return [snapshot for snapshot in snapshots if account_id is None or snapshot.account_id == account_id]

    def list_records(
        self,
        *,
        account_id: str | None = None,
    ) -> list[dict]:
        # Snapshots are an audit trail. The table view exposes one row per
        # account/date, with the latest successful collection winning.
        records_by_key: dict[tuple[str, str], dict] = {}
        for snapshot in self.list_snapshots(account_id=account_id):
            if snapshot.status != "completed":
                continue
            for record in snapshot.records:
                item = record.model_dump(mode="json")
                item.update({
                    "snapshot_id": snapshot.snapshot_id,
                    "collected_at": snapshot.collected_at,
                    "data_end_date": snapshot.data_end_date or max(
                        snapshot_record.date for snapshot_record in snapshot.records
                    ),
                })
                records_by_key.setdefault((item["account_id"], item["date"]), item)
        records = list(records_by_key.values())
        records.sort(
            key=lambda item: (
                item["collected_at"],
                item["date"],
                item["account_name"],
            ),
            reverse=True,
        )
        return records

    def _value(self) -> dict:
        value = self._store.read()
        return value if isinstance(value, dict) else {"snapshots": []}


class LyricTemplateRepository:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, default=[])

    def list(self, account_id: str | None = None) -> list[LyricTemplateConfig]:
        templates = [LyricTemplateConfig.model_validate(item) for item in self._store.read()]
        return [template for template in templates if account_id is None or template.account_id == account_id]

    def get(self, template_id: str) -> LyricTemplateConfig:
        for template in self.list():
            if template.id == template_id:
                return template
        raise NotFoundError(f"歌词模板不存在: {template_id}")

    def create(self, template: LyricTemplateConfig) -> LyricTemplateConfig:
        templates = self.list()
        self._ensure_unique(template, templates)
        templates.append(template)
        self._persist(templates)
        return template

    def update(self, template_id: str, template: LyricTemplateConfig) -> LyricTemplateConfig:
        templates = self.list()
        self._ensure_unique(template, templates, ignored_id=template_id)
        for index, current in enumerate(templates):
            if current.id == template_id:
                updated = template.model_copy(update={"id": template_id})
                templates[index] = updated
                self._persist(templates)
                return updated
        raise NotFoundError(f"歌词模板不存在: {template_id}")

    def delete(self, template_id: str) -> None:
        templates = self.list()
        remaining = [template for template in templates if template.id != template_id]
        if len(remaining) == len(templates):
            raise NotFoundError(f"歌词模板不存在: {template_id}")
        self._persist(remaining)

    def delete_for_account(self, account_id: str) -> None:
        self._persist([template for template in self.list() if template.account_id != account_id])

    def _ensure_unique(
        self,
        template: LyricTemplateConfig,
        templates: list[LyricTemplateConfig],
        ignored_id: str | None = None,
    ) -> None:
        for current in templates:
            if current.id == ignored_id:
                continue
            if current.account_id == template.account_id and current.name == template.name:
                raise ConflictError(f"模板名称已存在: {template.name}")

    def _persist(self, templates: list[LyricTemplateConfig]) -> None:
        self._store.write([template.model_dump(mode="json") for template in templates])
