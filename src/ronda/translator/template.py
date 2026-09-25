"""Tradutor determinístico: incidente + decisão → mensagem em português.

É a reserva do tradutor com LLM (Fase 4): nunca falha, nunca demora e diz sempre as três coisas
(o que houve, por que a prioridade, ação sugerida). Texto puro, sem Markdown: nome de arquivo e
código trazem `_`, `*` e `[]`, que o Telegram recusa em `parse_mode`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from jinja2 import Environment, PackageLoader, StrictUndefined

from ronda.domain.event import Evento
from ronda.domain.incident import Incidente
from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria
from ronda.governance.engine import Decisao
from ronda.governance.trace import formatar_duracao

LIMITE_TELEGRAM = 4096

EMOJI = {Prioridade.P1: "🔴", Prioridade.P2: "🟠", Prioridade.P3: "🟡", Prioridade.P4: "⚪"}

TITULO = {
    Categoria.comprometimento: "Possível comprometimento de máquina",
    Categoria.ataque_web: "Ataque a aplicação web",
    Categoria.negacao_servico: "Negação de serviço",
    Categoria.forca_bruta: "Tentativas de senha (força bruta)",
    Categoria.reconhecimento: "Varredura (reconhecimento)",
    Categoria.exfiltracao: "Possível saída de dados (exfiltração)",
    Categoria.benigno: "Atividade legítima",
    Categoria.desconhecido: "Alerta sem categoria conhecida",
}

ACAO = {
    Categoria.comprometimento: (
        "Isole a máquina da rede, preserve os logs e verifique processos, usuários e tarefas "
        "agendadas criados no período."
    ),
    Categoria.ataque_web: (
        "Confira o log de acesso da aplicação no período, procure arquivos novos no diretório "
        "web (webshell) e bloqueie o IP de origem no proxy ou no WAF."
    ),
    Categoria.negacao_servico: (
        "Verifique se o serviço segue respondendo, limite as requisições do IP de origem e acione "
        "o provedor se o volume vier de muitas origens."
    ),
    Categoria.forca_bruta: (
        "Bloqueie o IP de origem (fail2ban ou firewall), confira se algum login teve sucesso "
        "depois das falhas e exija senha forte ou MFA na conta visada."
    ),
    Categoria.reconhecimento: (
        "Normalmente não exige ação imediata. Confirme que só os serviços necessários estão "
        "expostos e acompanhe se a varredura vira tentativa de exploração."
    ),
    Categoria.exfiltracao: (
        "Trate como incidente de dados: identifique a máquina de origem, bloqueie o destino (DNS "
        "ou IP) e verifique quais dados ela alcança."
    ),
    Categoria.benigno: "Nenhuma ação necessária; registrado para referência.",
    Categoria.desconhecido: (
        "Revise o alerta original no painel e, se ele se repetir, peça o mapeamento da "
        "assinatura na taxonomia."
    ),
}

_ambiente = Environment(
    loader=PackageLoader("ronda.translator", "templates"),
    autoescape=False,  # texto puro para o Telegram, sem HTML
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
    keep_trailing_newline=False,
)


def tamanho_telegram(texto: str) -> int:
    """O Telegram conta o limite em unidades UTF-16: um emoji como 🟠 conta 2."""
    return len(texto.encode("utf-16-le")) // 2


def _truncar(texto: str) -> str:
    texto = texto.strip()
    if tamanho_telegram(texto) <= LIMITE_TELEGRAM:
        return texto
    sufixo = "\n… (mensagem cortada)"
    corpo = texto[: LIMITE_TELEGRAM - tamanho_telegram(sufixo)]
    while tamanho_telegram(corpo) + tamanho_telegram(sufixo) > LIMITE_TELEGRAM:
        corpo = corpo[:-1]
    return corpo.rstrip() + sufixo


def _o_que_houve(incidente: Incidente, evento: Evento | None) -> str:
    partes = []
    total = incidente.total_eventos
    duracao = incidente.atualizado_em - incidente.aberto_em
    partes.append(
        f"{total} evento{'s' if total != 1 else ''} de {incidente.origem}"
        + (f" em {formatar_duracao_curta(duracao)}" if duracao > timedelta(0) else "")
        + f", desde {incidente.aberto_em:%d/%m %H:%M} UTC."
    )
    if evento is not None:
        regra = evento.evidencias.get("regra") or {}
        suricata = evento.evidencias.get("suricata") or {}
        descricao = suricata.get("assinatura") or regra.get("descricao")
        if descricao:
            partes.append(f"Último alerta: {descricao}")
        if evento.ip_origem:
            partes.append(
                f"Origem: {evento.ip_origem}"
                + (f" → {evento.ip_destino}" if evento.ip_destino else "")
            )
    return "\n".join(partes)


def formatar_duracao_curta(duracao: timedelta) -> str:
    segundos = int(duracao.total_seconds())
    if segundos < 60:
        return f"{segundos} s"
    if segundos < 3600:
        return f"{segundos // 60} min"
    if segundos < 86400:
        return f"{segundos // 3600} h {segundos % 3600 // 60} min"
    return f"{segundos // 86400} d {segundos % 86400 // 3600} h"


def _porque(decisao: Decisao) -> list[str]:
    # O rastro é a explicação: cada passo do motor vira uma linha.
    return [p.texto for p in decisao.rastro.passos if p.etapa != "categoria"]


def mensagem_incidente(incidente: Incidente, decisao: Decisao, evento: Evento | None = None) -> str:
    prioridade = incidente.prioridade or decisao.prioridade
    return _truncar(
        _ambiente.get_template("incidente.txt.j2").render(
            emoji=EMOJI[prioridade],
            prioridade=prioridade.value,
            titulo=TITULO[incidente.categoria],
            ativo=incidente.ativo or "ativo não identificado",
            prazo=formatar_duracao(decisao.resposta) if decisao.resposta else None,
            o_que_houve=_o_que_houve(incidente, evento),
            porque=_porque(decisao),
            acao=ACAO[incidente.categoria],
            incidente_curto=str(incidente.id)[:8],
            tenant=incidente.tenant_id,
        )
    )


@dataclass(frozen=True)
class ItemResumo:
    incidente: Incidente

    @property
    def titulo(self) -> str:
        return TITULO[self.incidente.categoria]

    @property
    def ativo(self) -> str:
        return self.incidente.ativo or "ativo não identificado"

    @property
    def eventos(self) -> int:
        return self.incidente.total_eventos


def mensagem_agrupada(
    tenant: str, origem: str, prioridade: Prioridade, incidentes: list[Incidente], janela: timedelta
) -> str:
    categorias = {i.categoria for i in incidentes}
    acao = (
        ACAO[next(iter(categorias))]
        if len(categorias) == 1
        else ("Veja cada incidente no painel; se forem da mesma origem externa, bloqueie o IP.")
    )
    return _truncar(
        _ambiente.get_template("agrupado.txt.j2").render(
            emoji=EMOJI[prioridade],
            prioridade=prioridade.value,
            origem=origem,
            janela=formatar_duracao_curta(janela),
            itens=[ItemResumo(i) for i in incidentes],
            acao=acao,
            tenant=tenant,
        )
    )


def resumo_diario(
    tenant: str, dia: datetime, prioridade: Prioridade, incidentes: list[Incidente]
) -> str:
    por_categoria: dict[Categoria, list[ItemResumo]] = defaultdict(list)
    for incidente in incidentes:
        por_categoria[incidente.categoria].append(ItemResumo(incidente))
    grupos = [
        {"titulo": TITULO[c], "itens": itens}
        for c, itens in sorted(por_categoria.items(), key=lambda kv: -len(kv[1]))
    ]
    return _truncar(
        _ambiente.get_template("resumo.txt.j2").render(
            data=f"{dia:%d/%m/%Y}",
            prioridade=prioridade.value,
            itens=[i for g in grupos for i in g["itens"]],
            grupos=grupos,
            tenant=tenant,
        )
    )
