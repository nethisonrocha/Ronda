import pytest

from ronda.domain.incident import Contexto
from ronda.domain.priority import Criticidade, Impacto, Prioridade, Urgencia
from ronda.governance.engine import Motor
from ronda.governance.policy import ler_politica

# IPs dentro das redes da política demo.
PAGAMENTOS = "10.0.1.5"
WEB = "10.0.0.5"
TESTES = "10.0.9.20"
EXTERNO = "203.0.113.7"


def test_exemplo_da_especificacao_dos_contra_servidor_de_pagamentos(politica_demo, evento):
    decisao = Motor(politica_demo).avaliar(evento(ip_origem=EXTERNO, ip_destino=PAGAMENTOS))

    assert decisao.prioridade is Prioridade.P1
    assert decisao.ativo == "servidor-pagamentos"
    assert decisao.impacto is Impacto.alto
    assert decisao.urgencia is Urgencia.alta
    assert decisao.rastro.resumo == (
        "negacao_servico → ativo servidor-pagamentos (criticidade alta) → impacto alto"
        " → urgência alta → P1, resposta em 15 min"
    )


def test_exemplo_da_especificacao_mesmo_dos_contra_ambiente_de_testes(politica_demo, evento):
    decisao = Motor(politica_demo).avaliar(evento(ip_destino=TESTES))
    assert decisao.prioridade is Prioridade.P3
    assert decisao.rastro.resumo.endswith("P3, resposta em 24 h")


@pytest.mark.parametrize(
    ("categoria", "ip", "esperado"),
    [
        # Sem contexto, comprometimento não chega a P1 (A5): o sudo de rotina e o da escalada
        # são o mesmo alerta.
        ("comprometimento", PAGAMENTOS, Prioridade.P2),
        ("comprometimento", TESTES, Prioridade.P3),
        ("ataque_web", WEB, Prioridade.P2),
        ("negacao_servico", WEB, Prioridade.P2),
        ("forca_bruta", PAGAMENTOS, Prioridade.P3),
        ("forca_bruta", WEB, Prioridade.P4),
        ("reconhecimento", PAGAMENTOS, Prioridade.P4),
        ("benigno", PAGAMENTOS, Prioridade.P4),
    ],
)
def test_matriz_da_politica_demo(politica_demo, evento, categoria, ip, esperado):
    assert Motor(politica_demo).avaliar(evento(categoria=categoria, ip_destino=ip)).prioridade is (
        esperado
    )


def test_recorrencia_sobe_a_urgencia(politica_demo, evento):
    motor = Motor(politica_demo)
    forca_bruta = evento(categoria="forca_bruta", ip_destino=PAGAMENTOS)

    # Força bruta tem limiar próprio (A1): 5 falhas por dia é usuário errando a senha.
    sem = motor.avaliar(forca_bruta, Contexto(recorrencia_24h=49))
    com = motor.avaliar(forca_bruta, Contexto(recorrencia_24h=50))

    assert (sem.urgencia, sem.prioridade) == (Urgencia.media, Prioridade.P3)
    assert (com.urgencia, com.prioridade) == (Urgencia.alta, Prioridade.P2)
    assert "recorrencia_24h >= 50 (só forca_bruta): urgência sobe para alta" in com.rastro.resumo
    assert "recorrencia_24h >= 5" not in sem.rastro.resumo  # o limiar geral não vale para ela


@pytest.mark.parametrize(
    ("contexto", "esperado"),
    [
        (Contexto(), Prioridade.P2),
        (Contexto(recorrencia_24h=9), Prioridade.P2),  # repetir sudo não é sinal de ataque
        (Contexto(fora_do_horario=True), Prioridade.P1),
        (Contexto(ataque_previo_no_ativo=True), Prioridade.P1),
    ],
)
def test_comprometimento_so_vira_p1_com_contexto(politica_demo, evento, contexto, esperado):
    decisao = Motor(politica_demo).avaliar(
        evento(categoria="comprometimento", ip_destino=PAGAMENTOS), contexto
    )
    assert decisao.prioridade is esperado


def test_modificador_no_teto_fica_registrado_sem_efeito(politica_demo, evento):
    decisao = Motor(politica_demo).avaliar(
        evento(categoria="forca_bruta", ip_destino=PAGAMENTOS),
        Contexto(recorrencia_24h=50, confirmado=True),
    )
    assert decisao.urgencia is Urgencia.alta
    assert "confirmado: urgência já em alta, sem efeito" in decisao.rastro.resumo


def test_modificador_que_desce_a_urgencia(evento):
    politica = ler_politica(
        _politica(
            urgencia={
                "base": {"forca_bruta": "alta"},
                "modificadores": [{"se": "fora_do_horario", "descer": 1}],
            }
        )
    )
    decisao = Motor(politica).avaliar(
        evento(tenant_id="acme", categoria="forca_bruta"), Contexto(fora_do_horario=True)
    )
    assert decisao.urgencia is Urgencia.media
    assert "fora_do_horario: urgência desce para media" in decisao.rastro.resumo


def test_ativo_pelo_nome_informado_pela_fonte(politica_demo, evento):
    decisao = Motor(politica_demo).avaliar(evento(ativo="servidor-pagamentos", ip_destino=TESTES))
    assert decisao.ativo == "servidor-pagamentos"
    assert decisao.rastro.passos[1].dados == {"via": "nome"}


def test_ativo_pelo_ip_de_origem_quando_o_destino_e_externo(politica_demo, evento):
    # Máquina interna comprometida falando com a internet.
    decisao = Motor(politica_demo).avaliar(
        evento(categoria="comprometimento", ip_origem=PAGAMENTOS, ip_destino=EXTERNO)
    )
    assert decisao.ativo == "servidor-pagamentos"
    assert decisao.rastro.passos[1].dados == {"via": "ip_origem"}


def test_rede_mais_especifica_vence(evento):
    politica = ler_politica(
        _politica(
            ativos=[
                {"nome": "rede-toda", "rede": "10.0.0.0/8", "criticidade": "baixa"},
                {"nome": "banco", "rede": "10.0.5.10/32", "criticidade": "alta"},
            ]
        )
    )
    motor = Motor(politica)
    assert motor.avaliar(evento(tenant_id="acme", ip_destino="10.0.5.10")).ativo == "banco"
    assert motor.avaliar(evento(tenant_id="acme", ip_destino="10.0.5.11")).ativo == "rede-toda"


def test_ipv6_nao_casa_com_rede_ipv4(evento):
    politica = ler_politica(
        _politica(ativos=[{"nome": "tudo", "rede": "0.0.0.0/0", "criticidade": "alta"}])
    )
    decisao = Motor(politica).avaliar(evento(tenant_id="acme", ip_destino="::1"))
    assert decisao.ativo is None


def test_ativo_fora_do_inventario_usa_criticidade_padrao(politica_demo, evento):
    motor = Motor(politica_demo)

    desconhecido = motor.avaliar(evento(ativo="impressora", ip_destino=EXTERNO))
    assert desconhecido.criticidade is Criticidade.media
    assert "ativo impressora fora do inventário (criticidade padrão media)" in (
        desconhecido.rastro.resumo
    )

    sem_ativo = motor.avaliar(evento())
    assert "ativo não identificado (criticidade padrão media)" in sem_ativo.rastro.resumo
    assert sem_ativo.prioridade is Prioridade.P2  # negacao_servico x media → medio x alta


def test_categoria_sem_regra_usa_prioridade_base_da_taxonomia(evento):
    politica = ler_politica(_politica())  # sem impacto nem urgência para nada
    decisao = Motor(politica).avaliar(evento(tenant_id="acme", categoria="ataque_web"))

    assert decisao.prioridade is Prioridade.P1
    assert decisao.prioridade_base is True
    assert decisao.impacto is None and decisao.urgencia is None
    assert "sem regra de impacto e urgência na política v1, vale a prioridade base P1" in (
        decisao.rastro.resumo
    )


def test_p4_sem_prazo_de_resposta(politica_demo, evento):
    decisao = Motor(politica_demo).avaliar(evento(categoria="benigno"))
    assert decisao.resposta is None
    assert decisao.rastro.resumo.endswith("P4, sem prazo de resposta")


def test_evento_de_outro_tenant_e_recusado(politica_demo, evento):
    with pytest.raises(ValueError, match="tenant"):
        Motor(politica_demo).avaliar(evento(tenant_id="acme"))


def test_mesma_entrada_mesma_decisao(politica_demo, evento):
    motor = Motor(politica_demo)
    e = evento(ip_destino=PAGAMENTOS)
    assert motor.avaliar(e, Contexto(confirmado=True)) == motor.avaliar(
        e, Contexto(confirmado=True)
    )


def _politica(**extra):
    return {
        "tenant": "acme",
        "versao": 1,
        "matriz": {
            "alto": {"alta": "P1", "media": "P2", "baixa": "P3"},
            "medio": {"alta": "P2", "media": "P3", "baixa": "P4"},
            "baixo": {"alta": "P3", "media": "P4", "baixa": "P4"},
        },
        "impacto": {"forca_bruta": {"alta": "alto", "media": "medio", "baixa": "baixo"}},
    } | extra
