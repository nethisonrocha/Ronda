"""Contrato dos canais de notificação e o canal falso dos testes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ErroCanal(RuntimeError):
    """Falha ao enviar. A mensagem nunca carrega token nem URL com token."""


@dataclass(frozen=True)
class Mensagem:
    destino: str
    texto: str
    botao: str | None = None
    """Dados do botão "Reconhecer" (callback), ou None para mensagem sem botão."""


class Canal(Protocol):
    def enviar(self, mensagem: Mensagem) -> str:
        """Envia e devolve o id da mensagem no canal."""
        ...


@dataclass
class CanalFalso:
    """Guarda o que seria enviado. `falhar` faz as próximas N chamadas falharem."""

    enviadas: list[Mensagem] = field(default_factory=list)
    falhar: int = 0

    def enviar(self, mensagem: Mensagem) -> str:
        if self.falhar > 0:
            self.falhar -= 1
            raise ErroCanal("canal falso: falha simulada")
        self.enviadas.append(mensagem)
        return f"falso-{len(self.enviadas)}"
