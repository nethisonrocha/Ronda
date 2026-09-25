"""Escalas ITIL: criticidade do ativo, impacto, urgência e prioridade P1–P4."""

from __future__ import annotations

from enum import StrEnum
from typing import Self


class _Escala(StrEnum):
    """Escala ordenada, declarada do nível mais baixo para o mais alto."""

    def deslocar(self, passos: int) -> Self:
        """Sobe (passos > 0) ou desce (passos < 0) na escala, parando nas pontas."""
        niveis = list(type(self))
        indice = niveis.index(self) + passos
        return niveis[max(0, min(len(niveis) - 1, indice))]


class Criticidade(_Escala):
    baixa = "baixa"
    media = "media"
    alta = "alta"


class Impacto(_Escala):
    baixo = "baixo"
    medio = "medio"
    alto = "alto"


class Urgencia(_Escala):
    baixa = "baixa"
    media = "media"
    alta = "alta"


class Prioridade(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

    @property
    def nivel(self) -> int:
        """1 é o mais grave."""
        return int(self.value[1])
