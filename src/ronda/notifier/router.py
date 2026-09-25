"""Política anti-fadiga: o que fazer com cada subida de prioridade, e o que enviar agora. Puro.

- **Modo por prioridade** (política do tenant): P1 imediata, P2 agrupada, P3 no resumo diário,
  P4 nunca (fica só no dashboard).
- **Silêncio por origem:** depois de notificar uma origem (mesma origem, categoria e ativo, a
  chave do incidente), um incidente novo da mesma chave no mesmo nível ou abaixo, dentro de
  `silencio_por_origem`, é registrado como suprimido. Subir de nível sempre notifica.
- **Horário de silêncio:** nada sai, exceto o P1; o resto espera o fim do horário.
- **Agrupamento:** P2 da mesma origem (ferramenta) esperam a janela de `agrupamento` e saem numa
  mensagem só.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ronda.domain.incident import Incidente
from ronda.domain.notification import EstadoNotificacao, ModoNotificacao, Notificacao
from ronda.domain.priority import Prioridade
from ronda.governance.policy import RegrasNotificacao
from ronda.governance.trace import formatar_duracao
from ronda.notifier.digest import resumo_vencido


@dataclass(frozen=True)
class Classificacao:
    modo: ModoNotificacao
    estado: EstadoNotificacao
    motivo: str | None = None


def classificar(
    regras: RegrasNotificacao,
    prioridade: Prioridade,
    mais_grave_da_origem: Notificacao | None,
    agora: datetime,
) -> Classificacao | None:
    """None quando a prioridade não notifica nunca (P4 no padrão).

    `mais_grave_da_origem` é a notificação mais grave da mesma chave dentro da janela de
    silêncio: comparar com a mais recente deixaria passar um P2 logo depois de um P3 que veio
    depois de outro P2.
    """
    modo = regras.modos[prioridade]
    if modo == "nunca":
        return None
    modo = ModoNotificacao(modo)
    if mais_grave_da_origem is not None:
        decorrido = agora - mais_grave_da_origem.criada_em
        mesmo_nivel_ou_abaixo = prioridade.nivel >= mais_grave_da_origem.prioridade.nivel
        if decorrido < regras.silencio_por_origem and mesmo_nivel_ou_abaixo:
            return Classificacao(
                modo,
                EstadoNotificacao.suprimida,
                f"silêncio por origem: {mais_grave_da_origem.prioridade.value} da mesma origem "
                f"notificado há {formatar_duracao_segura(decorrido)}",
            )
    return Classificacao(modo, EstadoNotificacao.pendente)


def formatar_duracao_segura(duracao) -> str:
    return formatar_duracao(duracao) if duracao.total_seconds() >= 60 else "menos de 1 min"


def em_silencio(regras: RegrasNotificacao, agora: datetime) -> bool:
    if regras.horario_silencio is None:
        return False
    local = agora.astimezone(regras.zona).time()
    inicio, fim = regras.horario_silencio.inicio, regras.horario_silencio.fim
    if inicio <= fim:
        return inicio <= local < fim
    return local >= inicio or local < fim  # atravessa a meia-noite


class TipoEnvio(StrEnum):
    individual = "individual"
    agrupado = "agrupado"
    resumo = "resumo"


@dataclass(frozen=True)
class Envio:
    tipo: TipoEnvio
    prioridade: Prioridade
    itens: tuple[tuple[Notificacao, Incidente], ...]
    origem: str | None = None


def planejar(
    regras: RegrasNotificacao,
    pendentes: list[tuple[Notificacao, Incidente]],
    agora: datetime,
    ultimo_resumo: datetime | None,
) -> list[Envio]:
    """O que sai agora. O que não sai continua pendente para a próxima rodada."""
    silencio = em_silencio(regras, agora)
    envios: list[Envio] = []
    agrupadas: dict[tuple[str, Prioridade], list[tuple[Notificacao, Incidente]]] = defaultdict(list)
    resumo: list[tuple[Notificacao, Incidente]] = []

    for item in sorted(pendentes, key=lambda x: (x[0].criada_em, str(x[0].id))):
        notificacao, incidente = item
        if notificacao.modo is ModoNotificacao.imediata:
            if not silencio or notificacao.prioridade is Prioridade.P1:
                envios.append(Envio(TipoEnvio.individual, notificacao.prioridade, (item,)))
        elif notificacao.modo is ModoNotificacao.agrupada:
            agrupadas[(incidente.origem, notificacao.prioridade)].append(item)
        else:
            resumo.append(item)

    if not silencio:
        for (origem, prioridade), itens in agrupadas.items():
            if itens[0][0].criada_em + regras.agrupamento > agora:
                continue  # a janela ainda está aberta
            tipo = TipoEnvio.agrupado if len(itens) > 1 else TipoEnvio.individual
            envios.append(Envio(tipo, prioridade, tuple(itens), origem=origem))
        if resumo and resumo_vencido(regras, agora, ultimo_resumo, resumo[0][0].criada_em):
            mais_grave = min((n.prioridade for n, _ in resumo), key=lambda p: p.nivel)
            envios.append(Envio(TipoEnvio.resumo, mais_grave, tuple(resumo)))
    return envios
