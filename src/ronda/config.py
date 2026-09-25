"""Configuração lida do ambiente (veja .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    policies_dir: Path


def carregar_config() -> Config:
    return Config(policies_dir=Path(os.environ.get("RONDA_POLICIES_DIR", "policies/examples")))
