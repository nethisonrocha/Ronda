"""Notificador ligado ao pipeline, com canal falso e relógio controlado."""

from datetime import UTC, datetime, timedelta

import pytest

from ronda.domain.incident import EstadoIncidente
from ronda.domain.notification import EstadoNotificacao, ModoNotificacao
from ronda.governance.policy import RepositorioPoliticas
from ronda.notifier.channels.base import CanalFalso
from ronda.notifier.channels.telegram import dados_do_botao
from ronda.notifier.service import Notificador, processar_atualizacao
from ronda.storage.repositories import (
    RepositorioAuditoria,
    RepositorioIncidentes,
    RepositorioNotificacoes,
)
from ronda.workers.pipeline import Pipeline
from tests.conftest import POLITICAS_EXEMPLO

EVENTO_T0 = datetime(2022, 1, 21, 10, 0, tzinfo=UTC)
MEIO_DIA_LOCAL = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)  # 12:00 em Fortaleza
CHAT = "999"


class Relogio:
    def __init__(self, agora):
        self.agora = agora

    def __call__(self):
        return self.agora

    def avancar(self, **delta):
        self.agora += timedelta(**delta)


@pytest.fixture
def relogio():
    return Relogio(MEIO_DIA_LOCAL)


@pytest.fixture
def canal():
    return CanalFalso()


@pytest.fixture
def notificador(banco, canal, relogio):
    return Notificador(
        banco,
        RepositorioPoliticas(POLITICAS_EXEMPLO),
        {"telegram": canal},
        relogio=relogio,
        ambiente={"RONDA_TELEGRAM_CHAT_DEMO": CHAT},
    )


@pytest.fixture
def pipeline(banco, notificador):
    return Pipeline(
        banco, RepositorioPoliticas(POLITICAS_EXEMPLO), ao_priorizar=notificador.ao_priorizar
    )


def gerar(pipeline, evento, categoria, ip, minuto=0, n=1):
    resultado = None
    for i in range(n):
        resultado = pipeline.processar_evento(
            evento(
                categoria=categoria,
                ip_destino=ip,
                ocorrido_em=EVENTO_T0 + timedelta(minutes=minuto + i),
            )
        )
    return resultado


def notificacoes(banco):
    with banco.sessao("demo") as sessao:
        consulta = RepositorioNotificacoes(sessao)
        return [
            n for i in RepositorioIncidentes(sessao).listar() for n in consulta.do_incidente(i.id)
        ]


def test_p1_sai_na_hora_com_botao_e_fica_registrado(pipeline, notificador, canal, banco, evento):
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")  # DoS no servidor de pagamentos
    assert notificador.despachar() == 1

    [mensagem] = canal.enviadas
    assert mensagem.destino == CHAT and mensagem.botao.startswith("r:")
    assert mensagem.texto.startswith("🔴 P1 · Negação de serviço")
    [n] = notificacoes(banco)
    assert (n.estado, n.modo, n.id_externo) == (
        EstadoNotificacao.enviada,
        ModoNotificacao.imediata,
        "falso-1",
    )
    assert notificador.despachar() == 0  # nada sai duas vezes


def test_p2_da_mesma_origem_espera_a_janela_e_vai_junto(
    pipeline, notificador, canal, relogio, banco, evento
):
    gerar(pipeline, evento, "comprometimento", "10.0.9.20")  # P2 no ambiente de testes
    gerar(pipeline, evento, "ataque_web", "10.0.0.5", minuto=1)  # P2 no servidor web
    relogio.avancar(minutes=5)
    assert notificador.despachar() == 0  # a janela de 10 min ainda está aberta
    relogio.avancar(minutes=6)
    assert notificador.despachar() == 1

    [mensagem] = canal.enviadas
    assert mensagem.texto.startswith("🟠 2 incidentes P2 de wazuh")
    enviadas = notificacoes(banco)
    assert {n.estado for n in enviadas} == {EstadoNotificacao.enviada}
    assert len({n.id_externo for n in enviadas}) == 1


def test_p3_espera_o_resumo_das_oito(pipeline, notificador, canal, relogio, evento):
    gerar(pipeline, evento, "forca_bruta", "10.0.1.5")  # P3
    assert notificador.despachar() == 0
    relogio.agora = datetime(2026, 9, 26, 11, 1, tzinfo=UTC)  # 08:01 do dia seguinte
    assert notificador.despachar() == 1
    [resumo] = canal.enviadas
    assert resumo.texto.startswith("📋 Resumo diário · 26/09/2026") and resumo.botao is None


def test_silencio_por_origem_suprime_o_incidente_novo_da_mesma_chave(
    pipeline, notificador, banco, evento
):
    gerar(pipeline, evento, "forca_bruta", "10.0.1.5", n=5)  # P3 e depois P2
    gerar(pipeline, evento, "forca_bruta", "10.0.1.5", minuto=60)  # 55 min depois: incidente novo

    por_estado = {}
    for n in notificacoes(banco):
        por_estado.setdefault(n.estado, []).append(n)
    [suprimida] = por_estado[EstadoNotificacao.suprimida]
    assert suprimida.motivo.startswith("silêncio por origem: P2 da mesma origem")


def test_no_horario_de_silencio_so_o_p1_sai(pipeline, notificador, canal, relogio, evento):
    relogio.agora = datetime(2026, 9, 25, 5, 0, tzinfo=UTC)  # 02:00 em Fortaleza
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")  # P1
    gerar(pipeline, evento, "comprometimento", "10.0.9.20", minuto=1)  # P2
    relogio.avancar(minutes=15)
    notificador.despachar()
    assert [m.texto.split(" ")[1] for m in canal.enviadas] == ["P1"]
    relogio.agora = datetime(2026, 9, 25, 10, 5, tzinfo=UTC)  # 07:05: o silêncio acabou
    notificador.despachar()
    assert [m.texto.split(" ")[1] for m in canal.enviadas] == ["P1", "P2"]


def test_p4_nao_gera_notificacao(pipeline, notificador, banco, evento):
    gerar(pipeline, evento, "benigno", "10.0.1.5")
    assert notificacoes(banco) == []


def test_reconhecer_pelo_botao_so_do_chat_certo_e_so_uma_vez(
    pipeline, notificador, canal, relogio, banco, evento
):
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")
    notificador.despachar()
    botao = canal.enviadas[0].botao
    relogio.avancar(minutes=12)

    assert (
        notificador.reconhecer(botao, "666", "intruso")
        == "Este chat não pode reconhecer este alerta."
    )
    assert notificador.reconhecer(botao, CHAT, "ana") == "Reconhecido ✅"
    assert notificador.reconhecer(botao, CHAT, "ana") == "Já estava reconhecido."
    assert notificador.reconhecer("r:naoehex", CHAT, "ana") == "Botão inválido."
    from uuid import uuid4

    assert notificador.reconhecer(dados_do_botao(uuid4()), CHAT, "ana") == "Alerta não encontrado."

    with banco.sessao("demo") as sessao:
        [incidente] = RepositorioIncidentes(sessao).listar()
        [auditoria] = RepositorioAuditoria(sessao).listar(
            entidade="incidente", entidade_id=incidente.id
        )[:1]
    assert incidente.estado is EstadoIncidente.reconhecido
    assert auditoria.acao == "incidente.reconhecido" and auditoria.ator == "telegram:ana"
    assert auditoria.dados["segundos_ate_reconhecer"] == int(
        (relogio.agora - incidente.aberto_em).total_seconds()
    )


def test_reconhecer_a_mensagem_agrupada_reconhece_todos(
    pipeline, notificador, canal, relogio, banco, evento
):
    gerar(pipeline, evento, "comprometimento", "10.0.9.20")
    gerar(pipeline, evento, "ataque_web", "10.0.0.5", minuto=1)
    relogio.avancar(minutes=11)
    notificador.despachar()
    assert notificador.reconhecer(canal.enviadas[0].botao, CHAT, "ana") == "Reconhecido ✅"
    assert all(n.reconhecida_por == "telegram:ana" for n in notificacoes(banco))


def test_falha_do_canal_tenta_de_novo_na_proxima_rodada(
    pipeline, notificador, canal, banco, evento
):
    canal.falhar = 1
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")
    assert notificador.despachar() == 0
    [n] = notificacoes(banco)
    assert (n.estado, n.tentativas) == (EstadoNotificacao.pendente, 1)
    assert notificador.despachar() == 1
    assert notificacoes(banco)[0].estado is EstadoNotificacao.enviada


def test_sem_destino_configurado_fica_suprimida_com_o_motivo(banco, canal, relogio, evento):
    notificador = Notificador(
        banco,
        RepositorioPoliticas(POLITICAS_EXEMPLO),
        {"telegram": canal},
        relogio=relogio,
        ambiente={},
    )
    pipeline = Pipeline(
        banco, RepositorioPoliticas(POLITICAS_EXEMPLO), ao_priorizar=notificador.ao_priorizar
    )
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")
    [n] = notificacoes(banco)
    assert n.estado is EstadoNotificacao.suprimida
    assert "RONDA_TELEGRAM_CHAT_DEMO" in n.motivo
    assert notificador.despachar() == 0 and canal.enviadas == []


def test_sem_canal_configurado_nada_sai_e_nada_se_perde(banco, relogio, evento):
    notificador = Notificador(
        banco,
        RepositorioPoliticas(POLITICAS_EXEMPLO),
        {},
        relogio=relogio,
        ambiente={"RONDA_TELEGRAM_CHAT_DEMO": CHAT},
    )
    pipeline = Pipeline(
        banco, RepositorioPoliticas(POLITICAS_EXEMPLO), ao_priorizar=notificador.ao_priorizar
    )
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")
    assert notificador.despachar() == 0
    assert notificacoes(banco)[0].estado is EstadoNotificacao.pendente


def test_clique_do_telegram_chega_ao_reconhecimento(pipeline, notificador, canal, evento):
    gerar(pipeline, evento, "negacao_servico", "10.0.1.5")
    notificador.despachar()
    respostas = []
    atualizacao = {
        "update_id": 1,
        "callback_query": {
            "id": "clique-1",
            "from": {"id": 7, "username": "ana"},
            "message": {"chat": {"id": int(CHAT)}},
            "data": canal.enviadas[0].botao,
        },
    }
    processar_atualizacao(atualizacao, notificador, lambda i, t: respostas.append((i, t)))
    processar_atualizacao(
        {"update_id": 2, "message": {"text": "oi"}},
        notificador,
        lambda i, t: respostas.append((i, t)),
    )
    assert respostas == [("clique-1", "Reconhecido ✅")]
