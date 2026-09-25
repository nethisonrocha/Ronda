"""Leitura dos cenários do AIT-ADS para a avaliação: alertas com os rótulos e o inventário.

- **Rótulos.** O CSV dos autores (`<cenario>_alerts.txt`), sem as linhas do AMiner, está na
  mesma ordem do `<cenario>_wazuh.json`: a linha *i* rotula o alerta *i*. `time_label` é a fase
  do ataque em cuja janela o alerta caiu (`false_positive` fora de qualquer uma); `event_label`
  diz se o ataque causou o alerta (`-` quando não causou).
- **Inventário.** Cada cenário tem os mesmos papéis de máquina com IPs diferentes; o CSV traz o
  IP de cada host. O nome do ativo usa hífen, como o `predecoder.hostname` do Wazuh
  (`intranet-server`, não `intranet_server`).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ronda.adapters.wazuh.adapter import horario_do_alerta
from ronda.domain.priority import Criticidade

CENARIOS = (
    "fox",
    "harrison",
    "russellmitchell",
    "santos",
    "shaw",
    "wardbeck",
    "wheeler",
    "wilson",
)
FORA_DE_ATAQUE = "false_positive"

CRITICIDADE_POR_PAPEL: dict[str, Criticidade] = {
    # Servidores que sustentam o negócio ou o perímetro.
    "intranet-server": Criticidade.alta,
    "webserver": Criticidade.alta,
    "mail": Criticidade.alta,
    "vpn": Criticidade.alta,
    "inet-firewall": Criticidade.alta,
    # Serviços de apoio.
    "internal-share": Criticidade.media,
    "cloud-share": Criticidade.media,
    "inet-dns": Criticidade.media,
}
"""Julgamento meu, não do dataset. As estações dos funcionários (`<nome>_mail`) ficam baixa."""

CRITICIDADE_ESTACAO = Criticidade.baixa


class RotulosDesalinhados(ValueError):
    """O CSV e o JSON não casam pela posição: os rótulos estariam no alerta errado."""


@dataclass(frozen=True)
class Rotulo:
    fase: str | None
    """Fase do ataque (`time_label`), ou None fora de qualquer janela de ataque."""
    causado: bool
    """O ataque causou o alerta (`event_label` diferente de `-`)."""


def _linhas_do_csv(diretorio: Path, cenario: str) -> Iterator[dict[str, str]]:
    with (diretorio / "csv" / f"{cenario}_alerts.txt").open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            if not linha["short"].startswith("A"):  # AMiner fica fora do Ronda
                yield linha


def nome_do_ativo(host: str) -> str:
    return host.replace("_", "-")


def inventario(diretorio: Path, cenario: str) -> list[dict[str, Any]]:
    """Ativos do cenário no formato da política: um por host, com o IP dele como /32."""
    ips: dict[str, str] = {}
    for linha in _linhas_do_csv(diretorio, cenario):
        ips.setdefault(linha["host"], linha["ip"])
    return [
        {
            "nome": nome_do_ativo(host),
            "rede": f"{ip}/32",
            "criticidade": CRITICIDADE_POR_PAPEL.get(
                nome_do_ativo(host), CRITICIDADE_ESTACAO
            ).value,
        }
        for host, ip in sorted(ips.items())
    ]


def fases(diretorio: Path, cenario: str) -> list[str]:
    """Fases do ataque do cenário, na ordem em que começam."""
    inicio: dict[str, int] = {}
    for linha in _linhas_do_csv(diretorio, cenario):
        fase = linha["time_label"]
        if fase != FORA_DE_ATAQUE:
            inicio[fase] = min(inicio.get(fase, int(linha["time"])), int(linha["time"]))
    return sorted(inicio, key=inicio.__getitem__)


def alertas_rotulados(
    diretorio: Path, cenario: str, conferir_a_cada: int = 1000
) -> Iterator[tuple[dict[str, Any], Rotulo]]:
    """Os alertas do JSON, na ordem do arquivo, cada um com o seu rótulo.

    Confere o horário de uma linha a cada `conferir_a_cada` e a contagem no fim: um
    desalinhamento poria o rótulo de uma fase no alerta de outra, em silêncio.
    """
    linhas = _linhas_do_csv(diretorio, cenario)
    caminho = diretorio / "json" / f"{cenario}_wazuh.json"
    with caminho.open(encoding="utf-8") as arquivo:
        posicao = 0
        for texto in arquivo:
            if not texto.strip():
                continue
            alerta = json.loads(texto)
            linha = next(linhas, None)
            if linha is None:
                raise RotulosDesalinhados(f"{cenario}: o JSON tem mais alertas que o CSV")
            if posicao % conferir_a_cada == 0:
                esperado = datetime.fromtimestamp(int(linha["time"]), UTC)
                diferenca = abs((horario_do_alerta(alerta) - esperado).total_seconds())
                if diferenca > 1:
                    raise RotulosDesalinhados(
                        f"{cenario}: alerta {posicao} às {horario_do_alerta(alerta)}, "
                        f"rótulo às {esperado}"
                    )
            fase = linha["time_label"]
            yield (
                alerta,
                Rotulo(
                    fase=None if fase == FORA_DE_ATAQUE else fase,
                    causado=linha["event_label"] != "-",
                ),
            )
            posicao += 1
    if next(linhas, None) is not None:
        raise RotulosDesalinhados(f"{cenario}: o CSV tem mais linhas que o JSON")
