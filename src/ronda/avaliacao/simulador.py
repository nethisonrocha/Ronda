"""O pipeline e o notificador em memória, no relógio do evento: a avaliação da fase 2.

As regras são as do worker, pelas mesmas funções puras:

- **correlação** por `CorrelacaoEmMemoria` (a mesma chave, janela e recorrência do banco);
- **prioridade** por `reavaliar`, só quando o incidente nasce ou o contexto muda, e a decisão
  conta só quando a prioridade efetiva sobe (ADR 0003);
- **notificação** por `classificar` na subida e por `planejar` a cada `intervalo_despacho`, com o
  silêncio por origem comparado à notificação mais grave da chave, como no repositório.

O que o banco faria e aqui não existe: o rastro gravado, a auditoria e o reconhecimento. O relógio
é sempre o do evento, porque 4 dias de AIT-ADS precisam passar por 4 dias de horário de silêncio
e 4 resumos diários, não por 10 minutos de relógio de parede.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from ronda.avaliacao.ait_ads import Rotulo
from ronda.correlation import (
    CorrelacaoEmMemoria,
    Reavaliacao,
    ativo_de_correlacao,
    montar_contexto,
    precisa_reavaliar,
    reavaliar,
)
from ronda.domain.event import Evento
from ronda.domain.incident import (
    JANELA_ATAQUE_PREVIO,
    Contexto,
    EstadoIncidente,
    Incidente,
    chave_correlacao,
)
from ronda.domain.notification import EstadoNotificacao, ModoNotificacao, Notificacao
from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria
from ronda.governance.engine import Motor
from ronda.governance.policy import Politica
from ronda.notifier.channels.base import Canal, CanalFalso, Mensagem
from ronda.notifier.channels.telegram import dados_do_botao
from ronda.notifier.router import Envio, TipoEnvio, classificar, planejar
from ronda.translator.template import mensagem_agrupada, mensagem_incidente, resumo_diario

DESTINO = "avaliacao"


@dataclass
class IncidenteSimulado:
    id: UUID
    tenant_id: str
    chave: str
    origem: str
    categoria: Categoria
    ativo: str | None
    aberto_em: datetime
    atualizado_em: datetime
    total: int = 0
    prioridade: Prioridade | None = None
    contexto: Contexto = field(default_factory=Contexto)
    decisoes: int = 0
    resolvido_em: datetime | None = None
    eventos_por_fase: Counter[str] = field(default_factory=Counter)
    causados_por_fase: Counter[str] = field(default_factory=Counter)
    avisado_em: datetime | None = None
    """Primeira mensagem que o incluiu (individual, agrupada ou resumo)."""
    grave_em: datetime | None = None
    """Quando chegou a P1 ou P2 pela primeira vez."""
    rotulo_da_subida: Rotulo | None = None
    """O rótulo do evento que o levou a P1 ou P2: diz qual fase gerou o incidente grave."""

    @property
    def de_ataque(self) -> bool:
        return bool(self.eventos_por_fase)

    def modelo(self) -> Incidente:
        return Incidente(
            id=self.id,
            tenant_id=self.tenant_id,
            origem=self.origem,
            categoria=self.categoria,
            ativo=self.ativo,
            estado=EstadoIncidente.resolvido if self.resolvido_em else EstadoIncidente.aberto,
            prioridade=self.prioridade,
            total_eventos=self.total,
            contexto=self.contexto,
            aberto_em=self.aberto_em,
            atualizado_em=self.atualizado_em,
            resolvido_em=self.resolvido_em,
        )


@dataclass
class Contagens:
    eventos: int = 0
    decisoes: int = 0
    notificacoes: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    """(modo, estado, prioridade) → quantidade; estado final: enviada, suprimida ou pendente."""
    sem_aviso: Counter[str] = field(default_factory=Counter)
    """Subidas de prioridade cujo modo é `nunca` (P4 no padrão): ficam só no painel."""
    motivos_supressao: Counter[str] = field(default_factory=Counter)
    mensagens: Counter[tuple[str, str]] = field(default_factory=Counter)
    """(tipo do envio, prioridade) → mensagens enviadas ao canal."""
    espera: dict[str, list[timedelta]] = field(default_factory=lambda: defaultdict(list))
    """Prioridade → espera de cada notificação enviada, do registro ao envio."""


class Simulador:
    def __init__(
        self,
        politica: Politica,
        canal: Canal | None = None,
        intervalo_despacho: timedelta = timedelta(minutes=1),
    ) -> None:
        self.politica = politica
        self.motor = Motor(politica)
        self.regras = politica.notificacao
        self.canal: Canal = canal if canal is not None else CanalFalso()
        self.intervalo = intervalo_despacho
        self.correlacao = CorrelacaoEmMemoria(politica.correlacao.janela)
        self.incidentes: dict[UUID, IncidenteSimulado] = {}
        self.contagens = Contagens()
        self._pendentes: list[Notificacao] = []
        self._conteudo: dict[UUID, tuple[Reavaliacao, Evento]] = {}
        self._avisadas_por_chave: dict[str, list[Notificacao]] = defaultdict(list)
        self._proximo_despacho: datetime | None = None
        self._ultimo_resumo: datetime | None = None
        self._ultimo_evento: datetime | None = None
        self._usa_ataque_previo = politica.usa("ataque_previo_no_ativo")
        self._graves_por_ativo: dict[str, dict[Categoria, datetime]] = defaultdict(dict)
        """Ativo → categoria → último evento de um incidente P1/P2 (o `ataque_previo_no_ativo`,
        como `RepositorioIncidentes.grave_de_outra_categoria`)."""

    # --- pipeline -------------------------------------------------------------------------

    def processar(self, evento: Evento, rotulo: Rotulo | None = None) -> IncidenteSimulado:
        self._despachar_ate(evento.ocorrido_em)
        self.contagens.eventos += 1
        if self._ultimo_evento is None or evento.ocorrido_em > self._ultimo_evento:
            self._ultimo_evento = evento.ocorrido_em

        ativo = ativo_de_correlacao(evento, self.motor.ativo_do_inventario(evento))
        chave = chave_correlacao(evento.origem, evento.categoria, ativo)
        observacao = self.correlacao.observar(chave, evento.ocorrido_em)
        if observacao.encerrado is not None:
            anterior_id, quando = observacao.encerrado
            self.incidentes[anterior_id].resolvido_em = quando
        incidente = self.incidentes.get(observacao.incidente_id)
        if incidente is None:
            incidente = IncidenteSimulado(
                id=observacao.incidente_id,
                tenant_id=evento.tenant_id,
                chave=chave,
                origem=evento.origem,
                categoria=evento.categoria,
                ativo=ativo,
                aberto_em=evento.ocorrido_em,
                atualizado_em=evento.ocorrido_em,
            )
            self.incidentes[incidente.id] = incidente
        incidente.total += 1
        incidente.atualizado_em = max(incidente.atualizado_em, evento.ocorrido_em)
        if rotulo is not None and rotulo.fase is not None:
            incidente.eventos_por_fase[rotulo.fase] += 1
            if rotulo.causado:
                incidente.causados_por_fase[rotulo.fase] += 1

        contexto = montar_contexto(
            incidente.contexto,
            self.politica,
            evento.ocorrido_em,
            observacao.recorrencia,
            self._ataque_previo(ativo, evento.categoria, evento.ocorrido_em),
        )
        if precisa_reavaliar(observacao.novo, incidente.contexto, contexto):
            reav = reavaliar(self.motor, evento, contexto, incidente.prioridade)
            if reav.subiu:
                self.contagens.decisoes += 1
                incidente.decisoes += 1
                incidente.prioridade = reav.prioridade
                incidente.contexto = contexto
                if incidente.grave_em is None and reav.prioridade.nivel <= 2:
                    incidente.grave_em = evento.ocorrido_em
                    incidente.rotulo_da_subida = rotulo
                self._ao_priorizar(incidente, reav, evento)
        incidente.contexto = contexto
        if ativo is not None and incidente.prioridade in (Prioridade.P1, Prioridade.P2):
            graves = self._graves_por_ativo[ativo]
            anterior = graves.get(incidente.categoria)
            if anterior is None or incidente.atualizado_em > anterior:
                graves[incidente.categoria] = incidente.atualizado_em
        return incidente

    def _ataque_previo(self, ativo: str | None, categoria: Categoria, instante: datetime) -> bool:
        if ativo is None or not self._usa_ataque_previo:
            return False
        desde = instante - JANELA_ATAQUE_PREVIO
        return any(
            outra != categoria and ultimo >= desde
            for outra, ultimo in self._graves_por_ativo.get(ativo, {}).items()
        )

    def finalizar(self, margem: timedelta = timedelta(days=1, hours=1)) -> None:
        """Deixa o relógio correr depois do último evento: o que esperava o fim do horário de
        silêncio, a janela do agrupamento ou o resumo das 8h sai agora."""
        if self._ultimo_evento is not None:
            self._despachar_ate(self._ultimo_evento + margem)
        for n in self._pendentes:
            self.contagens.notificacoes[(n.modo.value, "pendente", n.prioridade.value)] += 1

    # --- notificação ----------------------------------------------------------------------

    def _ao_priorizar(
        self, incidente: IncidenteSimulado, reav: Reavaliacao, evento: Evento
    ) -> None:
        regras = self.regras
        if regras is None or incidente.prioridade is None:
            return
        agora = evento.ocorrido_em
        classificacao = classificar(
            regras,
            incidente.prioridade,
            self._mais_grave(incidente.chave, agora - regras.silencio_por_origem),
            agora,
        )
        if classificacao is None:
            self.contagens.sem_aviso[incidente.prioridade.value] += 1
            return
        notificacao = Notificacao(
            tenant_id=incidente.tenant_id,
            incidente_id=incidente.id,
            decisao_id=uuid4(),
            canal=regras.canal,
            destino=DESTINO,
            prioridade=incidente.prioridade,
            modo=classificacao.modo,
            estado=classificacao.estado,
            motivo=classificacao.motivo,
            criada_em=agora,
        )
        if notificacao.estado is EstadoNotificacao.suprimida:
            chave = (notificacao.modo.value, "suprimida", notificacao.prioridade.value)
            self.contagens.notificacoes[chave] += 1
            self.contagens.motivos_supressao[(classificacao.motivo or "").split(":")[0]] += 1
            return
        self._avisadas_por_chave[incidente.chave].append(notificacao)
        self._pendentes.append(notificacao)
        if notificacao.modo is not ModoNotificacao.resumo_diario:
            self._conteudo[notificacao.id] = (reav, evento)
        if self._proximo_despacho is None:
            self._proximo_despacho = agora

    def _mais_grave(self, chave: str, desde: datetime) -> Notificacao | None:
        """Como `RepositorioNotificacoes.mais_grave_da_chave`: a não suprimida mais grave desde
        `desde`; entre as de mesma prioridade, a mais recente."""
        avisadas = self._avisadas_por_chave.get(chave)
        if not avisadas:
            return None
        recentes = [n for n in avisadas if n.criada_em >= desde]
        self._avisadas_por_chave[chave] = recentes
        if not recentes:
            return None
        return min(recentes, key=lambda n: (n.prioridade.nivel, -n.criada_em.timestamp()))

    def _despachar_ate(self, instante: datetime) -> None:
        while (
            self._pendentes
            and self._proximo_despacho is not None
            and self._proximo_despacho <= instante
        ):
            self._despachar(self._proximo_despacho)
            self._proximo_despacho += self.intervalo
        if not self._pendentes:
            self._proximo_despacho = None

    def _despachar(self, agora: datetime) -> None:
        if self.regras is None:
            return
        itens = [(n, self.incidentes[n.incidente_id]) for n in self._pendentes]
        # `planejar` só lê `origem` do incidente; o modelo completo sai apenas para o texto.
        envios = planejar(self.regras, itens, agora, self._ultimo_resumo)
        if not envios:
            return
        enviadas: set[UUID] = set()
        for envio in envios:
            self.canal.enviar(self._mensagem(envio, agora))
            self.contagens.mensagens[(envio.tipo.value, envio.prioridade.value)] += 1
            for n, incidente in envio.itens:
                enviadas.add(n.id)
                self.contagens.notificacoes[(n.modo.value, "enviada", n.prioridade.value)] += 1
                self.contagens.espera[n.prioridade.value].append(agora - n.criada_em)
                if incidente.avisado_em is None:
                    incidente.avisado_em = agora
                self._conteudo.pop(n.id, None)
            if envio.tipo is TipoEnvio.resumo:
                self._ultimo_resumo = agora
        self._pendentes = [n for n in self._pendentes if n.id not in enviadas]

    def _mensagem(self, envio: Envio, agora: datetime) -> Mensagem:
        regras = self.regras
        assert regras is not None
        primeira, incidente = envio.itens[0]
        incidentes = [i.modelo() for _, i in envio.itens]
        botao: str | None = dados_do_botao(primeira.id)
        if envio.tipo is TipoEnvio.individual and primeira.id in self._conteudo:
            reav, evento = self._conteudo[primeira.id]
            texto = mensagem_incidente(incidentes[0], reav.decisao, evento)
        elif envio.tipo is TipoEnvio.resumo:
            texto = resumo_diario(
                primeira.tenant_id, agora.astimezone(regras.zona), envio.prioridade, incidentes
            )
            botao = None
        else:
            texto = mensagem_agrupada(
                primeira.tenant_id,
                envio.origem or incidente.origem,
                envio.prioridade,
                incidentes,
                regras.agrupamento,
            )
        return Mensagem(destino=DESTINO, texto=texto, botao=botao)
