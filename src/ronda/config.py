"""Configuração do Ronda, lida de variáveis de ambiente e do arquivo .env (veja .env.example).

Variáveis de ambiente têm precedência sobre o .env. As URLs com senha não aparecem no repr
nem nas mensagens de erro; para registrar a configuração em log, use `Configuracao.resumo()`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import AnyUrl, Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["desenvolvimento", "teste", "producao"]


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # O .env também guarda variáveis do compose (RONDA_PG_PASSWORD etc.).
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    ambiente: Ambiente = Field(default="desenvolvimento", validation_alias="RONDA_ENV")
    diretorio_politicas: Path = Field(
        default=Path("policies/examples"),
        validation_alias="RONDA_POLICIES_DIR",
        description="Diretório com um arquivo <tenant>.yaml por organização",
    )
    url_banco: PostgresDsn | None = Field(
        default=None,
        validation_alias="RONDA_DATABASE_URL",
        repr=False,
        description="Conexão da aplicação: papel sem privilégios, sujeito à RLS",
    )
    url_banco_migracao: PostgresDsn | None = Field(
        default=None,
        validation_alias="RONDA_DATABASE_MIGRATION_URL",
        repr=False,
        description="Conexão das migrations: papel dono das tabelas",
    )
    url_redis: RedisDsn | None = Field(
        default=None,
        validation_alias="RONDA_REDIS_URL",
        repr=False,
        description="Redis das filas (Redis Streams)",
    )

    telegram_token: SecretStr | None = Field(
        default=None,
        validation_alias="RONDA_TELEGRAM_TOKEN",
        description="Token do bot do Ronda (não é o bot do Paperclip)",
    )
    cors_origens: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        validation_alias="RONDA_CORS_ORIGINS",
        description="Origens permitidas para CORS no dashboard",
    )

    @field_validator("cors_origens", mode="before")
    @classmethod
    def _parse_cors_origens(cls, valor: object) -> object:
        if isinstance(valor, str):
            return [item.strip() for item in valor.split(",") if item.strip()]
        return valor

    @field_validator("telegram_token", mode="before")
    @classmethod
    def _vazio_e_ausente(cls, valor: object) -> object:
        return None if isinstance(valor, str) and not valor.strip() else valor

    def resumo(self) -> dict[str, str | None]:
        """Configuração pronta para log, com as senhas mascaradas."""
        return {
            "ambiente": self.ambiente,
            "diretorio_politicas": str(self.diretorio_politicas),
            "url_banco": mascarar(self.url_banco),
            "url_banco_migracao": mascarar(self.url_banco_migracao),
            "url_redis": mascarar(self.url_redis),
            "telegram_token": "***" if self.telegram_token else None,
        }


def mascarar(url: AnyUrl | None) -> str | None:
    """Troca a senha da URL por ***; o resto fica legível."""
    if url is None:
        return None
    partes = urlsplit(str(url))
    if partes.password is None:
        return str(url)
    usuario = partes.username or ""
    endereco = partes.hostname or ""
    if partes.port is not None:
        endereco = f"{endereco}:{partes.port}"
    return urlunsplit(partes._replace(netloc=f"{usuario}:***@{endereco}"))


@lru_cache
def obter_configuracao() -> Configuracao:
    """Configuração do processo, lida uma vez."""
    return Configuracao()
