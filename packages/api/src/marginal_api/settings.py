"""Runtime settings, read from the environment once."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    write_token: str
    results: Path
    environment: str
    cors_origins: tuple[str, ...] = ()

    @property
    def token_required(self) -> bool:
        return bool(self.write_token)

    @property
    def model_paths(self) -> list[Path]:
        """The calibrated model when the calibration stage has run, else the uncalibrated one."""
        return [
            self.results / "calibrate" / "own_calibrated_model.json",
            self.results / "mmm" / "own_model.json",
        ]

    @property
    def registry_path(self) -> Path:
        return self.results / "experiments" / "registry.json"


def load_settings() -> Settings:
    root = Path(os.environ.get("MARGINAL_ROOT", Path(__file__).resolve().parents[4]))
    return Settings(
        database_url=os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/marginal"),
        write_token=os.environ.get("MARGINAL_WRITE_TOKEN", ""),
        results=root / "results",
        environment=os.environ.get("MARGINAL_ENV", "development"),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("MARGINAL_CORS_ORIGINS", "*").split(",") if o.strip()
        ),
    )
