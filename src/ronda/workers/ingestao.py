"""Ingestão pelo Redis Streams: a API publica, o worker consome em grupo.

Garantias:

- **Nada se perde.** O worker só dá `XACK` depois de processar. Se ele cair no meio, a
  mensagem fica pendente e outro consumidor a retoma (`XAUTOCLAIM`) depois de `ocioso_ms`.
- **Nada se duplica.** Reprocessar a mesma mensagem não cria um segundo evento: o id do evento
  é determinístico e o banco recusa a repetição (`id_origem`).
- **Nada trava o grupo.** Alerta inválido vai para a stream de erro com o motivo e é
  reconhecido. Falha transitória (banco fora, por exemplo) é tentada de novo até
  `max_entregas`; depois disso, também vai para a stream de erro.
- **A stream não cresce sem limite.** Mensagem reconhecida é apagada (`XDEL`); com o Redis em
  `noeviction`, uma stream que só crescesse acabaria recusando escrita.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import redis

from ronda.adapters.base import AlertaInvalido

STREAM = "ronda:ingestao"
STREAM_ERROS = "ronda:ingestao:erros"
GRUPO = "ronda-ingestao"
ORIGENS = ("wazuh",)

log = logging.getLogger(__name__)


class Resultado(StrEnum):
    gravado = "gravado"
    duplicado = "duplicado"
    ignorado = "ignorado"
    """O adaptador descartou o alerta de propósito (ex.: cópia do fast.log)."""


Processador = Callable[[str, str, Mapping[str, Any]], Resultado]
"""(tenant, origem, alerta) → resultado. Levanta AlertaInvalido para alerta sem conserto."""


class FilaIndisponivel(RuntimeError):
    pass


class FilaIngestao:
    """Lado da API: publica cada alerta como uma mensagem, sem converter nada."""

    def __init__(self, cliente: redis.Redis, stream: str = STREAM) -> None:
        self.cliente = cliente
        self.stream = stream

    def publicar(self, tenant: str, origem: str, alertas: Iterable[Mapping[str, Any]]) -> list[str]:
        recebido_em = datetime.now(UTC).isoformat()
        try:
            with self.cliente.pipeline(transaction=False) as pipe:
                for alerta in alertas:
                    pipe.xadd(
                        self.stream,
                        {
                            "tenant": tenant,
                            "origem": origem,
                            "recebido_em": recebido_em,
                            "alerta": json.dumps(alerta, ensure_ascii=False),
                        },
                    )
                return [str(i) for i in pipe.execute()]
        except redis.RedisError as erro:
            raise FilaIndisponivel(str(erro)) from erro


@dataclass
class Estatisticas:
    lidas: int = 0
    retomadas: int = 0
    resultados: dict[str, int] = field(default_factory=dict)
    erros: int = 0
    adiadas: int = 0
    """Falharam por motivo transitório e ficaram pendentes para nova tentativa."""

    def contar(self, resultado: Resultado) -> None:
        self.resultados[resultado.value] = self.resultados.get(resultado.value, 0) + 1

    def somar(self, outra: Estatisticas) -> None:
        self.lidas += outra.lidas
        self.retomadas += outra.retomadas
        self.erros += outra.erros
        self.adiadas += outra.adiadas
        for chave, n in outra.resultados.items():
            self.resultados[chave] = self.resultados.get(chave, 0) + n


def nome_do_consumidor() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class WorkerIngestao:
    def __init__(
        self,
        cliente: redis.Redis,
        processar: Processador,
        *,
        consumidor: str | None = None,
        stream: str = STREAM,
        stream_erros: str = STREAM_ERROS,
        grupo: str = GRUPO,
        lote: int = 100,
        bloquear_ms: int = 1000,
        ocioso_ms: int = 60_000,
        max_entregas: int = 5,
        depois_do_lote: Callable[[], None] | None = None,
    ) -> None:
        self.cliente = cliente
        self.processar = processar
        self.consumidor = consumidor or nome_do_consumidor()
        self.stream, self.stream_erros, self.grupo = stream, stream_erros, grupo
        self.lote, self.bloquear_ms = lote, bloquear_ms
        self.ocioso_ms, self.max_entregas = ocioso_ms, max_entregas
        self.depois_do_lote = depois_do_lote

    def garantir_grupo(self) -> None:
        try:
            self.cliente.xgroup_create(self.stream, self.grupo, id="0", mkstream=True)
        except redis.ResponseError as erro:
            if "BUSYGROUP" not in str(erro):
                raise

    def processar_lote(self, bloquear: bool = True) -> Estatisticas:
        """Retoma pendentes de consumidores parados e lê mensagens novas; processa tudo."""
        stats = Estatisticas()
        retomadas = self._retomar_pendentes()
        stats.retomadas = len(retomadas)
        novas = self.cliente.xreadgroup(
            self.grupo,
            self.consumidor,
            {self.stream: ">"},
            count=self.lote,
            block=self.bloquear_ms if bloquear and not retomadas else None,
        )
        mensagens = list(retomadas)
        for _, itens in novas or []:
            mensagens.extend(itens)
        for mensagem_id, campos in mensagens:
            stats.lidas += 1
            self._processar_mensagem(mensagem_id, campos, stats)
        if mensagens and self.depois_do_lote:
            self.depois_do_lote()
        return stats

    def rodar(self, parar: threading.Event | None = None) -> None:
        parar = parar or threading.Event()
        self.garantir_grupo()
        log.info("worker %s consumindo %s (grupo %s)", self.consumidor, self.stream, self.grupo)
        while not parar.is_set():
            try:
                self.processar_lote()
            except redis.ConnectionError as erro:
                log.warning("Redis indisponível (%s); tentando de novo", erro)
                parar.wait(2)

    # --- internos --------------------------------------------------------------------------

    def _retomar_pendentes(self) -> list[tuple[str, dict]]:
        resposta = self.cliente.xautoclaim(
            self.stream,
            self.grupo,
            self.consumidor,
            min_idle_time=self.ocioso_ms,
            start_id="0-0",
            count=self.lote,
        )
        mensagens = resposta[1] if resposta else []
        # Mensagem apagada enquanto pendente volta como (id, None); não há o que processar.
        return [(i, c) for i, c in mensagens if c]

    def _entregas(self, mensagem_id: str) -> int:
        pendente = self.cliente.xpending_range(
            self.stream, self.grupo, min=mensagem_id, max=mensagem_id, count=1
        )
        return int(pendente[0]["times_delivered"]) if pendente else 1

    def _reconhecer(self, mensagem_id: str) -> None:
        with self.cliente.pipeline() as pipe:
            pipe.xack(self.stream, self.grupo, mensagem_id)
            pipe.xdel(self.stream, mensagem_id)
            pipe.execute()

    def _para_erros(self, mensagem_id: str, campos: Mapping[str, Any], motivo: str) -> None:
        self.cliente.xadd(
            self.stream_erros,
            {
                **{k: v for k, v in campos.items() if k != "motivo"},
                "motivo": motivo[:2000],
                "mensagem_id": mensagem_id,
            },
        )
        self._reconhecer(mensagem_id)

    def _processar_mensagem(self, mensagem_id: str, campos: dict, stats: Estatisticas) -> None:
        tenant, origem = campos.get("tenant"), campos.get("origem")
        try:
            if not tenant or origem not in ORIGENS:
                raise AlertaInvalido(f"mensagem sem tenant ou com origem desconhecida: {origem!r}")
            try:
                alerta = json.loads(campos["alerta"])
            except (KeyError, json.JSONDecodeError) as erro:
                raise AlertaInvalido(f"alerta não é JSON: {erro}") from None
            if not isinstance(alerta, dict):
                raise AlertaInvalido("alerta não é um objeto JSON")
            resultado = self.processar(tenant, origem, alerta)
        except AlertaInvalido as erro:
            stats.erros += 1
            self._para_erros(mensagem_id, campos, f"alerta inválido: {erro}")
            return
        except Exception as erro:  # transitório até prova em contrário
            entregas = self._entregas(mensagem_id)
            if entregas >= self.max_entregas:
                stats.erros += 1
                log.error(
                    "mensagem %s falhou %d vezes; indo para a stream de erro", mensagem_id, entregas
                )
                self._para_erros(mensagem_id, campos, f"falhou {entregas} vezes: {erro!r}")
            else:
                stats.adiadas += 1
                log.warning("mensagem %s falhou (%s); fica pendente", mensagem_id, erro)
            return
        stats.contar(resultado)
        self._reconhecer(mensagem_id)
