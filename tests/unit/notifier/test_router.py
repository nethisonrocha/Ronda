from datetime import UTC, datetime, timedelta

import pytest

from ronda.domain.incident import Incidente
from ronda.domain.notification import EstadoNotificacao, ModoNotificacao, Notificacao
from ronda.domain.priority import Prioridade
from ronda.governance.policy import PoliticaInvalida, carregar_politica, ler_politica
from ronda.notifier.digest import momento_do_resumo, resumo_vencido
from ronda.notifier.router import TipoEnvio, classificar, em_silencio, planejar
from tests.conftest import POLITICAS_EXEMPLO

POLITICA = carregar_politica(POLITICAS_EXEMPLO / "demo.yaml")
REGRAS = POLITICA.notificacao
# Fortaleza é UTC−3: o silêncio 22:00–07:00 local é 01:00–10:00 UTC; o resumo das 08:00, 11:00 UTC.
MEIO_DIA_LOCAL = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)


def incidente(origem="wazuh", categoria="forca_bruta", **campos):
    return Incidente.model_validate(
        {
            "tenant_id": "demo",
            "origem": origem,
            "categoria": categoria,
            "ativo": "servidor-pagamentos",
            "aberto_em": MEIO_DIA_LOCAL,
            "atualizado_em": MEIO_DIA_LOCAL,
        }
        | campos
    )


def notificacao(inc, prioridade, modo, criada_em=MEIO_DIA_LOCAL, **campos):
    return Notificacao(
        tenant_id="demo",
        incidente_id=inc.id,
        canal="telegram",
        destino="123",
        prioridade=prioridade,
        modo=modo,
        criada_em=criada_em,
        **campos,
    )


def test_modo_por_prioridade_e_p4_nunca():
    assert classificar(REGRAS, Prioridade.P1, None, MEIO_DIA_LOCAL).modo is ModoNotificacao.imediata
    assert classificar(REGRAS, Prioridade.P2, None, MEIO_DIA_LOCAL).modo is ModoNotificacao.agrupada
    assert (
        classificar(REGRAS, Prioridade.P3, None, MEIO_DIA_LOCAL).modo
        is ModoNotificacao.resumo_diario
    )
    assert classificar(REGRAS, Prioridade.P4, None, MEIO_DIA_LOCAL) is None


def test_silencio_por_origem_suprime_mesmo_nivel_e_abaixo_mas_deixa_subir():
    anterior = notificacao(incidente(), Prioridade.P2, ModoNotificacao.agrupada)
    dez_min = MEIO_DIA_LOCAL + timedelta(minutes=10)

    mesmo = classificar(REGRAS, Prioridade.P2, anterior, dez_min)
    abaixo = classificar(REGRAS, Prioridade.P3, anterior, dez_min)
    acima = classificar(REGRAS, Prioridade.P1, anterior, dez_min)
    depois = classificar(REGRAS, Prioridade.P2, anterior, MEIO_DIA_LOCAL + timedelta(minutes=31))

    assert mesmo.estado is EstadoNotificacao.suprimida
    assert mesmo.motivo == "silêncio por origem: P2 da mesma origem notificado há 10 min"
    assert abaixo.estado is EstadoNotificacao.suprimida
    assert acima.estado is EstadoNotificacao.pendente
    assert depois.estado is EstadoNotificacao.pendente


@pytest.mark.parametrize(
    ("hora_utc", "silencio"),
    [(0, False), (1, True), (4, True), (9, True), (10, False), (15, False), (0.99, False)],
)
def test_horario_de_silencio_atravessa_a_meia_noite_no_fuso_do_tenant(hora_utc, silencio):
    instante = datetime(2026, 9, 25, tzinfo=UTC) + timedelta(hours=hora_utc)
    assert em_silencio(REGRAS, instante) is silencio


def test_sem_horario_de_silencio_nunca_esta_em_silencio():
    regras = REGRAS.model_copy(update={"horario_silencio": None})
    assert not em_silencio(regras, datetime(2026, 9, 25, 3, tzinfo=UTC))


def test_p1_sai_na_hora_ate_no_horario_de_silencio_e_o_p2_espera():
    madrugada = datetime(2026, 9, 25, 5, 0, tzinfo=UTC)  # 02:00 em Fortaleza
    p1 = incidente(categoria="negacao_servico")
    p2 = incidente(ativo="web")
    pendentes = [
        (notificacao(p1, Prioridade.P1, ModoNotificacao.imediata, madrugada), p1),
        (
            notificacao(
                p2, Prioridade.P2, ModoNotificacao.agrupada, madrugada - timedelta(hours=1)
            ),
            p2,
        ),
    ]
    envios = planejar(REGRAS, pendentes, madrugada, None)
    assert [(e.tipo, e.prioridade) for e in envios] == [(TipoEnvio.individual, Prioridade.P1)]
    # Às 07:30 local o silêncio acabou e a janela do P2 já passou.
    depois = planejar(REGRAS, pendentes[1:], datetime(2026, 9, 25, 10, 30, tzinfo=UTC), None)
    assert [e.tipo for e in depois] == [TipoEnvio.individual]


def test_p2_da_mesma_origem_espera_a_janela_e_sai_numa_mensagem_so():
    a, b, c = incidente(ativo="a"), incidente(ativo="b"), incidente(origem="suricata", ativo="c")
    pendentes = [
        (notificacao(a, Prioridade.P2, ModoNotificacao.agrupada, MEIO_DIA_LOCAL), a),
        (
            notificacao(
                b, Prioridade.P2, ModoNotificacao.agrupada, MEIO_DIA_LOCAL + timedelta(minutes=3)
            ),
            b,
        ),
        (
            notificacao(
                c, Prioridade.P2, ModoNotificacao.agrupada, MEIO_DIA_LOCAL + timedelta(minutes=1)
            ),
            c,
        ),
    ]
    assert planejar(REGRAS, pendentes, MEIO_DIA_LOCAL + timedelta(minutes=9), None) == []
    envios = planejar(REGRAS, pendentes, MEIO_DIA_LOCAL + timedelta(minutes=11), None)
    por_origem = {e.origem: e for e in envios}
    assert por_origem["wazuh"].tipo is TipoEnvio.agrupado and len(por_origem["wazuh"].itens) == 2
    assert por_origem["suricata"].tipo is TipoEnvio.individual  # grupo de um é mensagem individual


def test_resumo_diario_vence_as_oito_no_fuso_do_tenant():
    ontem_tarde = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)  # 17:00 local
    assert momento_do_resumo(REGRAS, datetime(2026, 9, 25, 10, 59, tzinfo=UTC)) == datetime(
        2026, 9, 24, 11, 0, tzinfo=UTC
    )
    assert momento_do_resumo(REGRAS, datetime(2026, 9, 25, 11, 0, tzinfo=UTC)) == datetime(
        2026, 9, 25, 11, 0, tzinfo=UTC
    )
    assert not resumo_vencido(REGRAS, datetime(2026, 9, 25, 10, 59, tzinfo=UTC), None, ontem_tarde)
    assert resumo_vencido(REGRAS, datetime(2026, 9, 25, 11, 1, tzinfo=UTC), None, ontem_tarde)
    ja_enviado = datetime(2026, 9, 25, 11, 1, tzinfo=UTC)
    assert not resumo_vencido(
        REGRAS, datetime(2026, 9, 25, 18, 0, tzinfo=UTC), ja_enviado, ontem_tarde
    )


def test_resumo_junta_os_p3_pendentes_numa_mensagem():
    itens = []
    for n in range(3):
        inc = incidente(ativo=f"h{n}", categoria="reconhecimento")
        itens.append(
            (
                notificacao(
                    inc,
                    Prioridade.P3,
                    ModoNotificacao.resumo_diario,
                    datetime(2026, 9, 24, 20, tzinfo=UTC),
                ),
                inc,
            )
        )
    envios = planejar(REGRAS, itens, datetime(2026, 9, 25, 12, 0, tzinfo=UTC), None)
    assert [(e.tipo, len(e.itens)) for e in envios] == [(TipoEnvio.resumo, 3)]


def test_politica_de_notificacao_validada():
    base = POLITICA.model_dump(mode="json")
    with pytest.raises(PoliticaInvalida, match="fuso"):
        ler_politica(base | {"notificacao": base["notificacao"] | {"fuso": "Marte/Olimpo"}})
    with pytest.raises(PoliticaInvalida, match="P1"):
        ler_politica(base | {"notificacao": base["notificacao"] | {"modos": {"P1": "nunca"}}})
    with pytest.raises(PoliticaInvalida, match="destino_env"):
        ler_politica(base | {"notificacao": base["notificacao"] | {"destino_env": "chat id 123"}})
    parcial = ler_politica(base | {"notificacao": base["notificacao"] | {"modos": {"P3": "nunca"}}})
    assert parcial.notificacao.modos[Prioridade.P2] == "agrupada"  # o resto vem do padrão
    sem_bloco = ler_politica({k: v for k, v in base.items() if k != "notificacao"})
    assert sem_bloco.notificacao is None
