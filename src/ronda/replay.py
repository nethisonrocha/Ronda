"""Replay: reenvia os alertas de um cenário do AIT-ADS ao endpoint de ingestão.

Os intervalos originais entre os alertas são respeitados, divididos pelo fator de
velocidade (`--velocidade 60` faz uma hora de alertas passar em um minuto; `0` envia sem
espera). Alertas que já deveriam ter saído vão juntos numa requisição, até `lote_max`, para o
replay acompanhar mesmo acelerado.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Any

import httpx

from ronda.adapters.wazuh.adapter import horario_do_alerta, iterar_jsonl

Enviar = Callable[[list[dict[str, Any]]], None]


class ReplayInterrompido(RuntimeError):
    pass


@dataclass
class ResultadoReplay:
    alertas: int = 0
    requisicoes: int = 0
    segundos: float = 0.0
    atraso_max: float = 0.0
    """Maior atraso, em segundos, entre o horário previsto e o envio."""


def caminho_do_cenario(dados: Path, cenario: str) -> Path:
    caminho = dados / f"{cenario}_wazuh.json"
    if not caminho.exists():
        raise FileNotFoundError(
            f"cenário {cenario!r} não encontrado em {dados} (veja data/README.md)"
        )
    return caminho


def alertas_do_cenario(
    caminho: Path, pular: int = 0, limite: int | None = None
) -> Iterator[tuple[datetime, dict[str, Any]]]:
    fim = None if limite is None else pular + limite
    for alerta in islice(iterar_jsonl(caminho), pular, fim):
        yield horario_do_alerta(alerta), alerta


def reproduzir(
    alertas: Iterable[tuple[datetime, dict[str, Any]]],
    enviar: Enviar,
    velocidade: float,
    *,
    lote_max: int = 500,
    relogio: Callable[[], float] = time.monotonic,
    dormir: Callable[[float], None] = time.sleep,
) -> ResultadoReplay:
    if velocidade < 0:
        raise ValueError("velocidade não pode ser negativa")
    resultado = ResultadoReplay()
    inicio_real = relogio()
    inicio_evento: datetime | None = None
    lote: list[dict[str, Any]] = []

    def despachar() -> None:
        if lote:
            enviar(list(lote))
            resultado.alertas += len(lote)
            resultado.requisicoes += 1
            lote.clear()

    for instante, alerta in alertas:
        if inicio_evento is None:
            inicio_evento = instante
        previsto = (
            0.0 if velocidade == 0 else (instante - inicio_evento).total_seconds() / velocidade
        )
        if previsto - (relogio() - inicio_real) > 0:
            despachar()  # o que já venceu sai antes de dormir
        # Recalculada depois do envio: se ele demorou, o replay pode já estar atrasado.
        espera = previsto - (relogio() - inicio_real)
        if espera > 0:
            dormir(espera)
        else:
            resultado.atraso_max = max(resultado.atraso_max, -espera)
        lote.append(alerta)
        if len(lote) >= lote_max:
            despachar()
    despachar()
    resultado.segundos = relogio() - inicio_real
    return resultado


def enviar_por_http(
    cliente: httpx.Client,
    url: str,
    token: str,
    *,
    tentativas: int = 5,
    dormir: Callable[[float], None] = time.sleep,
) -> Enviar:
    """Envio com nova tentativa em falha transitória (503, rede); 401 interrompe o replay."""
    cabecalhos = {"Authorization": f"Bearer {token}"}

    def enviar(lote: list[dict[str, Any]]) -> None:
        for tentativa in range(1, tentativas + 1):
            try:
                resposta = cliente.post(url, json=lote, headers=cabecalhos, timeout=30)
            except httpx.TransportError as erro:
                if tentativa == tentativas:
                    raise ReplayInterrompido(f"sem conexão com {url}: {erro}") from erro
                dormir(min(2**tentativa, 30))
                continue
            if resposta.status_code == 202:
                return
            if resposta.status_code in (401, 403):
                raise ReplayInterrompido("token recusado pelo endpoint (401); confira RONDA_TOKEN")
            if resposta.status_code < 500 or tentativa == tentativas:
                raise ReplayInterrompido(
                    f"endpoint respondeu {resposta.status_code}: {resposta.text[:200]}"
                )
            dormir(min(2**tentativa, 30))

    return enviar
