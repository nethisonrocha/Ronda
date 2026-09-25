from datetime import UTC, datetime, timedelta

import yaml

from ronda.avaliacao import ResultadoCenario, Rotulo, Simulador
from ronda.governance.policy import ler_politica
from ronda.notifier.channels.base import CanalFalso
from tests.conftest import POLITICAS_EXEMPLO

# Fortaleza é UTC−3: silêncio 22:00–07:00 local = 01:00–10:00 UTC; resumo das 08:00 = 11:00 UTC.
T0 = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)
PAGAMENTOS = "10.0.1.5"  # servidor-pagamentos, criticidade alta


def politica(**notificacao):
    dados = yaml.safe_load((POLITICAS_EXEMPLO / "demo.yaml").read_text(encoding="utf-8"))
    dados["notificacao"] |= notificacao
    return ler_politica(dados)


def em(minutos: float) -> datetime:
    return T0 + timedelta(minutes=minutos)


def simulador(**notificacao):
    canal = CanalFalso()
    return Simulador(politica(**notificacao), canal), canal


def test_p1_sai_na_hora_e_a_decisao_so_conta_quando_a_prioridade_sobe(evento):
    sim, canal = simulador()
    for minuto in range(3):
        sim.processar(
            evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=em(minuto))
        )
    sim.finalizar()

    assert len(sim.incidentes) == 1
    assert sim.contagens.decisoes == 1  # nasce P1; a recorrência muda, a prioridade não
    assert sim.contagens.mensagens == {("individual", "P1"): 1}
    assert canal.enviadas[0].texto.startswith("🔴 P1")
    assert canal.enviadas[0].botao is not None
    assert sim.contagens.espera["P1"] == [timedelta(0)]


def test_recorrencia_sobe_para_p2_que_sai_agrupado_e_o_p3_vai_para_o_resumo(evento):
    sim, canal = simulador()
    for minuto in range(5):
        sim.processar(
            evento(categoria="forca_bruta", ip_destino=PAGAMENTOS, ocorrido_em=em(minuto))
        )
    sim.finalizar()

    (incidente,) = sim.incidentes.values()
    assert incidente.prioridade.value == "P2"
    assert sim.contagens.decisoes == 2  # P3 ao nascer, P2 na 5ª ocorrência
    assert sim.contagens.mensagens == {("individual", "P2"): 1, ("resumo", "P3"): 1}
    # O P2 espera a janela do agrupamento (10 min); o P3, o resumo das 08:00 do dia seguinte.
    assert sim.contagens.espera["P2"] == [timedelta(minutes=10)]
    assert sim.contagens.espera["P3"] == [datetime(2026, 9, 26, 11, 0, tzinfo=UTC) - T0]
    assert "Resumo" in canal.enviadas[-1].texto
    assert canal.enviadas[-1].botao is None


def test_depois_da_janela_o_incidente_se_encerra_e_outro_nasce(evento):
    sim, _ = simulador()
    sim.processar(evento(ip_destino=PAGAMENTOS, ocorrido_em=em(0)))
    sim.processar(evento(ip_destino=PAGAMENTOS, ocorrido_em=em(31)))

    primeiro, segundo = sorted(sim.incidentes.values(), key=lambda i: i.aberto_em)
    assert primeiro.resolvido_em == em(30)
    assert segundo.resolvido_em is None


def test_no_horario_de_silencio_so_o_p1_sai(evento):
    sim, _ = simulador()
    madrugada = datetime(2026, 9, 26, 2, 0, tzinfo=UTC)  # 23:00 em Fortaleza
    sim.processar(evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=madrugada))
    for minuto in range(5):
        sim.processar(
            evento(
                categoria="forca_bruta",
                ip_destino=PAGAMENTOS,
                ocorrido_em=madrugada + timedelta(minutes=minuto),
            )
        )
    sim.finalizar()

    assert sim.contagens.espera["P1"] == [timedelta(0)]
    # O P2 nasceu às 02:04 UTC e só sai às 10:00 UTC, 07:00 em Fortaleza.
    assert sim.contagens.espera["P2"] == [timedelta(hours=7, minutes=56)]


def test_silencio_por_origem_so_age_quando_e_maior_que_a_janela(evento):
    def rodar(silencio):
        sim, _ = simulador(silencio_por_origem=silencio)
        for minuto in (0, 40):  # dois incidentes da mesma chave: 40 min > janela de 30 min
            sim.processar(
                evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=em(minuto))
            )
        sim.finalizar()
        return sim.contagens

    igual_a_janela = rodar("30min")
    assert igual_a_janela.mensagens == {("individual", "P1"): 2}

    maior = rodar("2h")
    assert maior.mensagens == {("individual", "P1"): 1}
    assert maior.notificacoes[("imediata", "suprimida", "P1")] == 1
    assert maior.motivos_supressao == {"silêncio por origem": 1}


def test_p4_fica_so_no_painel(evento):
    sim, canal = simulador()
    sim.processar(evento(categoria="reconhecimento", ip_destino="10.0.9.9", ocorrido_em=em(0)))
    sim.finalizar()
    assert sim.contagens.sem_aviso == {"P4": 1}
    assert canal.enviadas == []


def test_rotulos_por_fase_e_diagnostico_da_cobertura(evento):
    sim, _ = simulador()
    sim.processar(
        evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=em(0)),
        Rotulo(fase="service_stop", causado=True),
    )
    sim.processar(
        evento(categoria="reconhecimento", ip_destino="10.0.9.9", ocorrido_em=em(1)),
        Rotulo(fase="network_scans", causado=True),
    )
    sim.processar(
        evento(categoria="forca_bruta", ip_destino="10.0.9.9", ocorrido_em=em(2)),
        Rotulo(fase="cracking", causado=False),
    )
    sim.processar(evento(categoria="negacao_servico", ip_destino="10.0.0.9", ocorrido_em=em(3)))
    sim.finalizar()

    resultado = ResultadoCenario(
        cenario="teste",
        alertas=4,
        descartados=0,
        fases=["network_scans", "cracking", "service_stop"],
        simulador=sim,
        segundos=0,
    )
    por_fase = {linha["fase"]: linha for linha in resultado.cobertura()}
    assert por_fase["service_stop"]["diagnostico"] == "gerou P1/P2"
    assert por_fase["service_stop"]["gerou"] == "causa"
    assert por_fase["network_scans"]["diagnostico"] == "vista, mas P4"
    assert por_fase["cracking"]["diagnostico"] == "sem alerta causado pelo ataque"
    assert por_fase["cracking"]["pela_janela"] == "P4"

    resumo = resultado.resumo()
    assert resumo["incidentes"] == 4
    # O P2 de negação de serviço no servidor-web não tem evento de ataque: é ruído que acorda.
    assert resumo["graves_fora_de_ataque"] == 1
    assert resumo["graves_pela_causa"] == 1


def test_fase_que_cai_num_p1_ja_aberto_nao_conta_como_gerada(evento):
    sim, _ = simulador()
    # O incidente vira P1 antes do ataque; o evento da fase só se soma a ele.
    sim.processar(evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=em(0)))
    sim.processar(
        evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=em(5)),
        Rotulo(fase="service_stop", causado=True),
    )
    sim.finalizar()
    resultado = ResultadoCenario("teste", 2, 0, ["service_stop"], sim, 0)
    (linha,) = resultado.cobertura()
    assert linha["pela_causa"] == "P1"
    assert linha["gerou"] == "-"
    assert linha["diagnostico"] == "caiu num P1/P2 que já existia"
    assert resultado.resumo()["graves_fora_de_ataque"] == 1
