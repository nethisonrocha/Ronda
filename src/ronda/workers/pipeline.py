"""Pipeline do worker: persistir o evento, correlacionar, avaliar e gravar a decisão.

Tudo de um evento acontece numa transação do tenant: ou o evento entra com o incidente, a
recorrência e a decisão coerentes, ou nada entra. A decisão só é gravada quando a prioridade
efetiva do incidente sobe (ADR 0003): reavaliar a cada evento é barato, mas gravar 380 mil
decisões iguais para uma varredura não diz nada a ninguém.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ronda.adapters.wazuh import AdaptadorWazuh
from ronda.config import Configuracao
from ronda.correlation import (
    Acao,
    Reavaliacao,
    agrupar,
    ativo_de_correlacao,
    novo_incidente,
    precisa_reavaliar,
    reavaliar,
)
from ronda.domain.event import Evento
from ronda.domain.incident import Incidente
from ronda.domain.priority import Prioridade
from ronda.governance.engine import Motor
from ronda.governance.policy import Politica, RepositorioPoliticas
from ronda.storage.database import BancoDeDados
from ronda.storage.repositories import (
    DecisaoRegistrada,
    IncidenteAtivoExistente,
    RepositorioAuditoria,
    RepositorioDecisoes,
    RepositorioEventos,
    RepositorioIncidentes,
)
from ronda.workers.ingestao import Resultado

log = logging.getLogger(__name__)

AoPriorizar = Callable[[Session, Politica, Incidente, Reavaliacao, DecisaoRegistrada], None]
"""Chamado dentro da transação quando a prioridade do incidente sobe (o notificador entra aqui)."""


@dataclass(frozen=True)
class ResultadoPipeline:
    resultado: Resultado
    incidente_id: UUID | None = None
    novo_incidente: bool = False
    prioridade: Prioridade | None = None
    decisao_id: UUID | None = None


class Pipeline:
    def __init__(
        self,
        banco: BancoDeDados,
        politicas: RepositorioPoliticas,
        *,
        adaptadores: Mapping[str, Any] | None = None,
        ao_priorizar: AoPriorizar | None = None,
    ) -> None:
        self.banco = banco
        self.politicas = politicas
        self.adaptadores = adaptadores or {"wazuh": AdaptadorWazuh()}
        self.ao_priorizar = ao_priorizar
        self._marcas: dict[str, datetime] = {}
        """Evento mais recente visto por tenant: o relógio do encerramento por inatividade."""

    # O worker chama o pipeline como um Processador: (tenant, origem, alerta) → Resultado.
    def __call__(self, tenant: str, origem: str, alerta: Mapping[str, Any]) -> Resultado:
        evento = self.adaptadores[origem].converter_um(alerta, tenant)
        if evento is None:
            return Resultado.ignorado
        return self.processar_evento(evento).resultado

    def processar_evento(self, evento: Evento) -> ResultadoPipeline:
        politica = self.politicas.obter(evento.tenant_id)
        motor = Motor(politica)
        ativo = ativo_de_correlacao(evento, motor.ativo_do_inventario(evento))
        with self.banco.sessao(evento.tenant_id) as sessao:
            if not RepositorioEventos(sessao).registrar(evento):
                return ResultadoPipeline(Resultado.duplicado)
            incidentes = RepositorioIncidentes(sessao)
            incidente, novo = self._incidente_do_evento(sessao, incidentes, evento, ativo, politica)
            incidentes.vincular_evento(incidente.id, evento.id)
            contexto = incidente.contexto.model_copy(
                update={
                    "recorrencia_24h": incidentes.recorrencia(
                        incidente.chave_correlacao, ate=evento.ocorrido_em
                    )
                }
            )
            prioridade, decisao_id = incidente.prioridade, None
            if precisa_reavaliar(novo, incidente.contexto, contexto):
                reav = reavaliar(motor, evento, contexto, incidente.prioridade)
                if reav.subiu:
                    registrada = RepositorioDecisoes(sessao).registrar(
                        reav.decisao, evento_id=evento.id, incidente_id=incidente.id
                    )
                    incidentes.atualizar_prioridade(incidente.id, reav.prioridade, contexto)
                    RepositorioAuditoria(sessao).registrar(
                        "motor",
                        "incidente.priorizado",
                        "incidente",
                        incidente.id,
                        {
                            "de": incidente.prioridade.value if incidente.prioridade else None,
                            "para": reav.prioridade.value,
                            "decisao": str(registrada.id),
                            "recorrencia_24h": contexto.recorrencia_24h,
                        },
                    )
                    prioridade, decisao_id = reav.prioridade, registrada.id
                    if self.ao_priorizar:
                        atualizado = incidente.model_copy(
                            update={"prioridade": reav.prioridade, "contexto": contexto}
                        )
                        self.ao_priorizar(sessao, politica, atualizado, reav, registrada)
                else:
                    incidentes.atualizar_contexto(incidente.id, contexto)
            marca = self._marcas.get(evento.tenant_id)
            if marca is None or evento.ocorrido_em > marca:
                self._marcas[evento.tenant_id] = evento.ocorrido_em
            return ResultadoPipeline(Resultado.gravado, incidente.id, novo, prioridade, decisao_id)

    def encerrar_inativos(self) -> int:
        """Encerra, em cada tenant visto, os incidentes cuja janela passou antes do evento mais
        recente. Roda depois de cada lote do worker."""
        total = 0
        for tenant, marca in list(self._marcas.items()):
            janela = self.politicas.obter(tenant).correlacao.janela
            with self.banco.sessao(tenant) as sessao:
                incidentes = RepositorioIncidentes(sessao)
                for inativo in incidentes.inativos(antes_de=marca - janela):
                    total += self._encerrar(sessao, inativo, inativo.atualizado_em + janela)
        return total

    # --- internos --------------------------------------------------------------------------

    def _incidente_do_evento(
        self,
        sessao: Session,
        incidentes: RepositorioIncidentes,
        evento: Evento,
        ativo: str | None,
        politica: Politica,
    ) -> tuple[Incidente, bool]:
        for _ in range(3):
            atual = incidentes.ativo_por_chave(
                evento.origem, evento.categoria, ativo, bloquear=True
            )
            agrupamento = agrupar(evento.ocorrido_em, atual, politica.correlacao.janela)
            if agrupamento.acao is Acao.agregar:
                return atual, False
            if atual is not None:
                self._encerrar(sessao, atual, agrupamento.encerrar_anterior_em)
            try:
                return incidentes.abrir(novo_incidente(evento, ativo)), True
            except IncidenteAtivoExistente:
                # Outro worker abriu o incidente da chave entre a busca e a gravação.
                log.info("incidente da chave aberto em paralelo; tentando de novo")
        raise RuntimeError("não foi possível achar nem abrir o incidente da chave")

    @staticmethod
    def _encerrar(sessao: Session, incidente: Incidente, quando: datetime) -> int:
        if not RepositorioIncidentes(sessao).resolver(incidente.id, quando):
            return 0
        RepositorioAuditoria(sessao).registrar(
            "motor",
            "incidente.encerrado_por_inatividade",
            "incidente",
            incidente.id,
            {
                "ultimo_evento": incidente.atualizado_em.isoformat(),
                "encerrado_em": quando.isoformat(),
            },
        )
        return 1


def processador_do_pipeline(
    banco: BancoDeDados, configuracao: Configuracao, ao_priorizar: AoPriorizar | None = None
) -> tuple[Pipeline, Callable[[], None]]:
    """O pipeline e o gancho pós-lote do worker (encerrar inativos)."""
    pipeline = Pipeline(
        banco, RepositorioPoliticas(configuracao.diretorio_politicas), ao_priorizar=ao_priorizar
    )
    return pipeline, pipeline.encerrar_inativos
