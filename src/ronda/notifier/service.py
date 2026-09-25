"""Serviço de notificação: registra no pipeline, despacha depois do commit, trata o reconhecimento.

- `ao_priorizar` roda **dentro** da transação do pipeline e só grava a notificação (pendente ou
  suprimida, com o motivo). Nenhuma chamada ao Telegram acontece ali.
- `despachar` roda **depois** do commit, no worker: reserva as pendentes com `SKIP LOCKED` (dois
  workers nunca mandam a mesma mensagem), planeja pela política e envia.
- `reconhecer` trata o botão: só vale do chat que recebeu a mensagem, só o primeiro clique conta,
  e o tempo até o reconhecimento vai para a auditoria.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ronda.correlation import Reavaliacao
from ronda.domain.incident import Incidente
from ronda.domain.notification import EstadoNotificacao, ModoNotificacao, Notificacao
from ronda.governance.policy import (
    Politica,
    PoliticaNaoEncontrada,
    RegrasNotificacao,
    RepositorioPoliticas,
)
from ronda.notifier.channels.base import Canal, ErroCanal, Mensagem
from ronda.notifier.channels.telegram import dados_do_botao, ler_botao
from ronda.notifier.router import Envio, TipoEnvio, classificar, planejar
from ronda.storage.database import BancoDeDados
from ronda.storage.repositories import (
    DecisaoRegistrada,
    RepositorioAuditoria,
    RepositorioDecisoes,
    RepositorioEventos,
    RepositorioIncidentes,
    RepositorioNotificacoes,
)
from ronda.translator.template import mensagem_agrupada, mensagem_incidente, resumo_diario

log = logging.getLogger(__name__)

Relogio = Callable[[], datetime]


def agora_utc() -> datetime:
    return datetime.now(UTC)


class Notificador:
    def __init__(
        self,
        banco: BancoDeDados,
        politicas: RepositorioPoliticas,
        canais: Mapping[str, Canal],
        *,
        relogio: Relogio = agora_utc,
        ambiente: Mapping[str, str] | None = None,
        intervalo_despacho: float = 5.0,
    ) -> None:
        self.banco = banco
        self.politicas = politicas
        self.canais = dict(canais)
        self.relogio = relogio
        self.ambiente = os.environ if ambiente is None else ambiente
        self.intervalo_despacho = intervalo_despacho
        self._ultimo_despacho = 0.0
        self._trava = threading.Lock()
        self._avisados: set[str] = set()

    # --- dentro da transação do pipeline --------------------------------------------------

    def ao_priorizar(
        self,
        sessao: Session,
        politica: Politica,
        incidente: Incidente,
        reavaliacao: Reavaliacao,
        registrada: DecisaoRegistrada,
    ) -> None:
        regras = politica.notificacao
        if regras is None or incidente.prioridade is None:
            return
        agora = self.relogio()
        repositorio = RepositorioNotificacoes(sessao)
        classificacao = classificar(
            regras,
            incidente.prioridade,
            repositorio.mais_grave_da_chave(
                incidente.chave_correlacao, desde=agora - regras.silencio_por_origem
            ),
            agora,
        )
        if classificacao is None:
            return
        destino = self.ambiente.get(regras.destino_env, "").strip()
        estado, motivo = classificacao.estado, classificacao.motivo
        if not destino:
            estado = EstadoNotificacao.suprimida
            motivo = f"destino não configurado: defina {regras.destino_env} no ambiente"
        repositorio.registrar(
            Notificacao(
                tenant_id=incidente.tenant_id,
                incidente_id=incidente.id,
                decisao_id=registrada.id,
                canal=regras.canal,
                destino=destino or "-",
                prioridade=incidente.prioridade,
                modo=classificacao.modo,
                estado=estado,
                motivo=motivo,
                criada_em=agora,
            )
        )

    # --- depois do commit -----------------------------------------------------------------

    def despachar_se_devido(self) -> int:
        """Para o laço do worker: despacha no máximo a cada `intervalo_despacho` segundos."""
        agora = time.monotonic()
        if agora - self._ultimo_despacho < self.intervalo_despacho:
            return 0
        self._ultimo_despacho = agora
        return self.despachar()

    def despachar(self) -> int:
        with self._trava:
            enviados = 0
            for tenant in self.politicas.tenants():
                try:
                    regras = self.politicas.obter(tenant).notificacao
                except PoliticaNaoEncontrada:
                    continue
                if regras is None:
                    continue
                canal = self.canais.get(regras.canal)
                if canal is None:
                    if tenant not in self._avisados:
                        log.warning(
                            "tenant %s: canal %s não configurado; nada sai", tenant, regras.canal
                        )
                        self._avisados.add(tenant)
                    continue
                enviados += self._despachar_tenant(tenant, regras, canal)
            return enviados

    def _despachar_tenant(self, tenant: str, regras: RegrasNotificacao, canal: Canal) -> int:
        agora = self.relogio()
        enviados = 0
        with self.banco.sessao(tenant) as sessao:
            notificacoes = RepositorioNotificacoes(sessao)
            pendentes = notificacoes.reservar_pendentes(limite=500)
            if not pendentes:
                return 0
            incidentes = RepositorioIncidentes(sessao)
            itens = []
            for n in pendentes:
                incidente = incidentes.obter(n.incidente_id)
                if incidente is not None:
                    itens.append((n, incidente))
            ultimo_resumo = notificacoes.ultimo_envio(ModoNotificacao.resumo_diario.value)
            for envio in planejar(regras, itens, agora, ultimo_resumo):
                mensagem = self._mensagem(sessao, tenant, regras, envio)
                try:
                    id_externo = canal.enviar(mensagem)
                except ErroCanal as erro:
                    log.warning("tenant %s: envio falhou (%s)", tenant, erro)
                    for n, _ in envio.itens:
                        notificacoes.marcar_falha(n.id, str(erro))
                    continue
                for n, _ in envio.itens:
                    notificacoes.marcar_enviada(n.id, id_externo, agora)
                enviados += 1
        return enviados

    def _mensagem(
        self, sessao: Session, tenant: str, regras: RegrasNotificacao, envio: Envio
    ) -> Mensagem:
        primeira, incidente = envio.itens[0]
        botao = dados_do_botao(primeira.id)
        if envio.tipo is TipoEnvio.individual:
            registrada = (
                RepositorioDecisoes(sessao).obter(primeira.decisao_id)
                if primeira.decisao_id
                else None
            )
            evento = None
            if registrada is not None and registrada.evento_id is not None:
                evento = RepositorioEventos(sessao).obter(registrada.evento_id)
            if registrada is None:  # sem decisão não há rastro: resumo em uma linha
                texto = mensagem_agrupada(
                    tenant, incidente.origem, envio.prioridade, [incidente], regras.agrupamento
                )
            else:
                texto = mensagem_incidente(incidente, registrada.decisao, evento)
        elif envio.tipo is TipoEnvio.agrupado:
            texto = mensagem_agrupada(
                tenant,
                envio.origem or incidente.origem,
                envio.prioridade,
                [i for _, i in envio.itens],
                regras.agrupamento,
            )
        else:
            texto = resumo_diario(
                tenant,
                self.relogio().astimezone(regras.zona),
                envio.prioridade,
                [i for _, i in envio.itens],
            )
            botao = None  # resumo não se reconhece: nada ali é urgente
        return Mensagem(destino=primeira.destino, texto=texto, botao=botao)

    # --- reconhecimento -------------------------------------------------------------------

    def reconhecer(self, dados_botao: str | None, chat_id: str, usuario: str) -> str:
        """Trata o clique no botão. Devolve o texto curto que o Telegram mostra a quem clicou."""
        notificacao_id = ler_botao(dados_botao)
        if notificacao_id is None:
            return "Botão inválido."
        quando = self.relogio()
        for tenant in self.politicas.tenants():
            with self.banco.sessao(tenant) as sessao:
                notificacoes = RepositorioNotificacoes(sessao)
                notificacao = notificacoes.obter(notificacao_id)
                if notificacao is None:
                    continue
                if notificacao.destino != str(chat_id):
                    log.warning(
                        "reconhecimento recusado: chat diferente do destino (tenant %s)", tenant
                    )
                    return "Este chat não pode reconhecer este alerta."
                return self._reconhecer(sessao, notificacoes, notificacao, usuario, quando)
        return "Alerta não encontrado."

    @staticmethod
    def _reconhecer(
        sessao: Session,
        notificacoes: RepositorioNotificacoes,
        notificacao: Notificacao,
        usuario: str,
        quando: datetime,
    ) -> str:
        incidentes = RepositorioIncidentes(sessao)
        reconhecidos = 0
        for n in notificacoes.da_mesma_mensagem(notificacao):
            if not notificacoes.reconhecer(n.id, f"telegram:{usuario}", quando):
                continue
            reconhecidos += 1
            incidente = incidentes.obter(n.incidente_id)
            if incidente is not None and incidentes.reconhecer(incidente.id, quando):
                RepositorioAuditoria(sessao).registrar(
                    f"telegram:{usuario}",
                    "incidente.reconhecido",
                    "incidente",
                    incidente.id,
                    {
                        "notificacao": str(n.id),
                        "segundos_ate_reconhecer": int(
                            (quando - incidente.aberto_em).total_seconds()
                        ),
                    },
                )
        return "Reconhecido ✅" if reconhecidos else "Já estava reconhecido."


def processar_atualizacao(
    atualizacao: Mapping, notificador: Notificador, responder: Callable[[str, str], None]
) -> None:
    """Uma atualização do getUpdates: só os cliques em botão interessam."""
    clique = atualizacao.get("callback_query")
    if not clique:
        return
    mensagem = clique.get("message") or {}
    chat_id = str((mensagem.get("chat") or {}).get("id", ""))
    remetente = clique.get("from") or {}
    usuario = remetente.get("username") or str(remetente.get("id", "desconhecido"))
    texto = notificador.reconhecer(clique.get("data"), chat_id, usuario)
    responder(str(clique["id"]), texto)


def rodar_poller(canal, notificador: Notificador, parar: threading.Event, espera: int = 25) -> None:
    """Long polling dos cliques no Telegram (não precisa de URL pública)."""
    deslocamento: int | None = None
    while not parar.is_set():
        try:
            atualizacoes = canal.atualizacoes(deslocamento, espera=espera)
        except ErroCanal as erro:
            log.warning("getUpdates falhou (%s); tentando de novo", erro)
            parar.wait(5)
            continue
        for atualizacao in atualizacoes:
            deslocamento = int(atualizacao["update_id"]) + 1
            try:
                processar_atualizacao(atualizacao, notificador, canal.responder_clique)
            except Exception:
                log.exception("falha ao tratar a atualização %s", atualizacao.get("update_id"))
