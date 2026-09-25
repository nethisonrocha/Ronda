from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ronda.correlation import (
    Acao,
    CorrelacaoEmMemoria,
    agrupar,
    chave_do_evento,
    contar_recorrencia,
    elevar,
    encerrados_por_inatividade,
    novo_incidente,
    precisa_reavaliar,
    reavaliar,
)
from ronda.domain.event import Evento
from ronda.domain.incident import TETO_RECORRENCIA, Contexto, EstadoIncidente
from ronda.domain.priority import Prioridade
from ronda.governance.engine import Motor
from ronda.governance.policy import PoliticaInvalida, carregar_politica, ler_politica
from tests.conftest import POLITICAS_EXEMPLO

T0 = datetime(2022, 1, 21, 0, 0, tzinfo=UTC)
JANELA = timedelta(minutes=30)
POLITICA_DEMO = carregar_politica(POLITICAS_EXEMPLO / "demo.yaml")


def em(minutos: float) -> datetime:
    return T0 + timedelta(minutes=minutos)


# --- exemplos --------------------------------------------------------------------------


def test_chave_usa_o_inventario_depois_o_nome_e_por_fim_o_ip(evento):
    suricata = evento(origem="suricata", ip_destino="10.0.1.5", ip_origem="203.0.113.7")
    assert chave_do_evento(suricata, "servidor-pagamentos") == (
        "suricata|negacao_servico|servidor-pagamentos"
    )
    assert chave_do_evento(suricata) == "suricata|negacao_servico|10.0.1.5"
    assert chave_do_evento(evento(ativo="mail")) == "wazuh|negacao_servico|mail"
    assert chave_do_evento(evento()) == "wazuh|negacao_servico|-"


def test_agrupar_dentro_da_janela_e_no_limite_exato(evento):
    ativo = novo_incidente(evento(ocorrido_em=em(0)), "a")
    assert agrupar(em(10), None, JANELA).acao is Acao.abrir
    assert agrupar(em(10), ativo, JANELA).acao is Acao.agregar
    assert agrupar(em(30), ativo, JANELA).acao is Acao.agregar  # o limite ainda conta
    passou = agrupar(em(30.01), ativo, JANELA)
    assert passou.acao is Acao.abrir and passou.encerrar_anterior_em == em(30)


def test_reconhecido_continua_agregando_e_resolvido_nao(evento):
    ativo = novo_incidente(evento(ocorrido_em=em(0)), "a")
    reconhecido = ativo.model_copy(update={"estado": EstadoIncidente.reconhecido})
    resolvido = ativo.model_copy(update={"estado": EstadoIncidente.resolvido})
    assert agrupar(em(5), reconhecido, JANELA).acao is Acao.agregar
    assert agrupar(em(5), resolvido, JANELA).acao is Acao.abrir


def test_encerrados_por_inatividade_pela_marca(evento):
    velho = novo_incidente(evento(ocorrido_em=em(0)), "a")
    recente = novo_incidente(evento(ocorrido_em=em(50)), "b")
    encerrados = encerrados_por_inatividade([velho, recente], marca=em(60), janela=JANELA)
    assert encerrados == [(velho, em(30))]


def test_recorrencia_conta_as_ultimas_24h_e_satura():
    instantes = [em(-24 * 60), em(-60), em(0)]  # o de 24 h atrás exatas fica de fora
    assert contar_recorrencia(instantes, ate=em(0)) == 2
    assert contar_recorrencia([em(0)] * 5000, ate=em(0)) == TETO_RECORRENCIA


def test_elevar_so_sobe():
    assert elevar(None, Prioridade.P3) is Prioridade.P3
    assert elevar(Prioridade.P3, Prioridade.P1) is Prioridade.P1
    assert elevar(Prioridade.P1, Prioridade.P4) is Prioridade.P1


def test_em_memoria_abre_agrega_e_encerra():
    corr = CorrelacaoEmMemoria(JANELA)
    a = corr.observar("k", em(0))
    b = corr.observar("k", em(20))
    c = corr.observar("k", em(80))  # 60 min depois do último: novo incidente
    assert a.novo and not b.novo and c.novo
    assert a.incidente_id == b.incidente_id != c.incidente_id
    assert c.encerrado == (a.incidente_id, em(50))
    assert (a.recorrencia, b.recorrencia, c.recorrencia) == (
        1,
        2,
        3,
    )  # recorrência cruza incidentes
    assert corr.encerrar_inativos(marca=em(200)) == [(c.incidente_id, em(110))]
    assert corr.observar("k", em(201)).novo


def test_reavaliacao_sobe_com_a_recorrencia_e_nunca_desce(politica_demo, evento):
    motor = Motor(politica_demo)
    e = evento(categoria="forca_bruta", ip_destino="10.0.1.5")  # P3; com recorrência ≥ 5, P2
    primeira = reavaliar(motor, e, Contexto(recorrencia_24h=1), None)
    assert (primeira.prioridade, primeira.subiu) == (Prioridade.P3, True)
    segunda = reavaliar(motor, e, Contexto(recorrencia_24h=5), primeira.prioridade)
    assert (segunda.prioridade, segunda.subiu) == (Prioridade.P2, True)
    # Mais tarde a recorrência cai abaixo do limiar: o motor diria P3, o incidente fica P2.
    terceira = reavaliar(motor, e, Contexto(recorrencia_24h=2), segunda.prioridade)
    assert terceira.decisao.prioridade is Prioridade.P3
    assert (terceira.prioridade, terceira.subiu) == (Prioridade.P2, False)


def test_so_reavalia_quando_nasce_ou_quando_o_contexto_muda():
    assert precisa_reavaliar(True, Contexto(), Contexto())
    assert precisa_reavaliar(False, Contexto(recorrencia_24h=1), Contexto(recorrencia_24h=2))
    assert not precisa_reavaliar(False, Contexto(recorrencia_24h=2), Contexto(recorrencia_24h=2))


def test_politica_janela_padrao_limites_e_teto_da_recorrencia(politica_demo):
    assert politica_demo.correlacao.janela == timedelta(minutes=30)
    base = politica_demo.model_dump(mode="json")
    for janela in ("30s", "8d"):
        with pytest.raises(PoliticaInvalida, match="janela"):
            ler_politica(base | {"correlacao": {"janela": janela}})
    with pytest.raises(PoliticaInvalida, match="satura"):
        ler_politica(
            base
            | {
                "urgencia": base["urgencia"]
                | {"modificadores": [{"se": "recorrencia_24h >= 5000", "subir": 1}]}
            }
        )
    assert ler_politica(base | {"correlacao": {"janela": "2h"}}).correlacao.janela == timedelta(
        hours=2
    )


# --- propriedades ----------------------------------------------------------------------

minutos_ordenados = st.lists(
    st.floats(0, 60 * 24 * 3, allow_nan=False), min_size=1, max_size=60
).map(sorted)
janelas = st.integers(1, 180).map(lambda m: timedelta(minutes=m))


@settings(max_examples=300, deadline=None)
@given(minutos_ordenados, janelas)
def test_propriedade_incidentes_separados_so_por_intervalos_maiores_que_a_janela(minutos, janela):
    corr = CorrelacaoEmMemoria(janela)
    instantes = [em(m) for m in minutos]
    ids = [corr.observar("k", t).incidente_id for t in instantes]

    lacunas = sum(1 for a, b in pairwise(instantes) if b - a > janela)
    assert len(set(ids)) == 1 + lacunas
    for (a, ia), (b, ib) in pairwise(zip(instantes, ids, strict=True)):
        assert (ia == ib) == (b - a <= janela)


@settings(max_examples=200, deadline=None)
@given(
    st.lists(st.tuples(st.sampled_from("abc"), st.floats(0, 600, allow_nan=False)), max_size=80),
    janelas,
)
def test_propriedade_todo_evento_em_um_incidente_da_propria_chave(eventos, janela):
    corr = CorrelacaoEmMemoria(janela)
    por_incidente: dict = {}
    nascimentos = 0
    for chave, minuto in sorted(eventos, key=lambda e: e[1]):
        obs = corr.observar(chave, em(minuto))
        por_incidente.setdefault(obs.incidente_id, set()).add(chave)
        nascimentos += obs.novo
    assert all(len(chaves) == 1 for chaves in por_incidente.values())
    assert nascimentos == len(por_incidente)  # cada incidente nasce uma vez só


@settings(max_examples=300, deadline=None)
@given(minutos_ordenados, st.integers(1, 8))
def test_propriedade_recorrencia_igual_a_contagem_por_forca_bruta(minutos, teto):
    corr = CorrelacaoEmMemoria(JANELA, teto=teto)
    instantes = [em(m) for m in minutos]
    for i, t in enumerate(instantes):
        obtida = corr.observar("k", t).recorrencia
        bruta = min(teto, sum(1 for s in instantes[: i + 1] if t - timedelta(hours=24) < s <= t))
        assert obtida == bruta


@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from(
        [
            "comprometimento",
            "ataque_web",
            "negacao_servico",
            "forca_bruta",
            "reconhecimento",
            "exfiltracao",
            "benigno",
            "desconhecido",
        ]
    ),
    st.sampled_from(["10.0.1.5", "10.0.0.5", "10.0.9.20", "203.0.113.7"]),
    st.lists(st.tuples(st.integers(0, TETO_RECORRENCIA), st.booleans()), min_size=1, max_size=25),
)
def test_propriedade_prioridade_do_incidente_aberto_nunca_diminui(categoria, ip, contextos):
    motor = Motor(POLITICA_DEMO)
    e = Evento(tenant_id="demo", origem="wazuh", categoria=categoria, ip_destino=ip, ocorrido_em=T0)
    atual = None
    historico = []
    for recorrencia, confirmado in contextos:
        r = reavaliar(motor, e, Contexto(recorrencia_24h=recorrencia, confirmado=confirmado), atual)
        if atual is not None:
            assert r.prioridade.nivel <= atual.nivel  # nunca menos grave
        assert r.subiu == (r.prioridade != atual)
        atual = r.prioridade
        historico.append(r.decisao.prioridade.nivel)
    assert atual.nivel == min(historico)  # fica com a mais grave que o motor já disse
