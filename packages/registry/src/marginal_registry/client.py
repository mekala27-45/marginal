"""Registering experiments and posting results: through the live API when it answers, into the
results folder when it does not, with the same record either way and the route recorded."""

from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from pathlib import Path

import httpx
from marginal_experiments.registration import ExperimentRecord, ResultRecord


def api_base() -> str | None:
    base = os.environ.get("MARGINAL_API_BASE", "").rstrip("/")
    return base or None


def write_token() -> str:
    return os.environ.get("MARGINAL_WRITE_TOKEN", "")


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


class Registry:
    def __init__(self, local_path: Path) -> None:
        self.local_path = local_path
        self.base = api_base()

    def _load(self) -> dict[str, list[dict[str, object]]]:
        if self.local_path.exists():
            loaded: dict[str, list[dict[str, object]]] = json.loads(
                self.local_path.read_text(encoding="utf-8")
            )
            return loaded
        return {"experiments": [], "results": []}

    def _save(self, store: dict[str, list[dict[str, object]]]) -> None:
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(
            json.dumps(store, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

    def register(self, name: str, kind: str, plan_hash: str, design: dict[str, object]) -> ExperimentRecord:
        payload = {"name": name, "kind": kind, "plan_hash": plan_hash, "design": design}
        if self.base:
            try:
                response = httpx.post(
                    f"{self.base}/v1/experiments",
                    json=payload,
                    headers={"Authorization": f"Bearer {write_token()}"},
                    timeout=20.0,
                )
                if response.status_code == 201:
                    body = response.json()
                    record = ExperimentRecord(
                        experiment_id=str(body["experiment_id"]),
                        name=name,
                        kind=kind,
                        plan_hash=plan_hash,
                        design=design,
                        registered_at=str(body["registered_at"]),
                        registered_via="api",
                    )
                    self._append("experiments", record.model_dump(mode="json"))
                    return record
            except httpx.HTTPError:
                pass
        record = ExperimentRecord(
            experiment_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"marginal:{kind}:{plan_hash}")),
            name=name,
            kind=kind,
            plan_hash=plan_hash,
            design=design,
            registered_at=_now(),
            registered_via="local",
        )
        self._append("experiments", record.model_dump(mode="json"))
        return record

    def post_result(self, record: ResultRecord) -> str:
        """Returns the route the result took: 'api' or 'local'."""
        via = "local"
        if self.base:
            try:
                response = httpx.post(
                    f"{self.base}/v1/experiments/{record.experiment_id}/result",
                    json=record.model_dump(mode="json"),
                    headers={"Authorization": f"Bearer {write_token()}"},
                    timeout=20.0,
                )
                if response.status_code == 201:
                    via = "api"
            except httpx.HTTPError:
                via = "local"
        self._append("results", {**record.model_dump(mode="json"), "posted_via": via})
        return via

    def _append(self, bucket: str, item: dict[str, object]) -> None:
        store = self._load()
        store[bucket] = [
            x
            for x in store[bucket]
            if x.get("experiment_id") != item.get("experiment_id")
            or bucket == "results"
            and x.get("method") != item.get("method")
        ]
        store[bucket].append(item)
        self._save(store)

    def experiments(self) -> list[dict[str, object]]:
        return self._load()["experiments"]

    def results(self) -> list[dict[str, object]]:
        return self._load()["results"]
