from datetime import UTC, datetime, timedelta

from ronda.domain.event import Evento
from ronda.domain.incident import Contexto, Incidente
from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria
from ronda.governance.engine import Motor
from ronda.governance.policy import carregar_politica
from ronda.translator.template import (
    ACAO,
    LIMITE_TELEGRAM,
    TITULO,
    mensagem_agrupada,
    mensagem_incidente,
    resumo_diario,
    tamanho_telegram,
)
from tests.conftest import POLITICAS_EXEMPLO

T0 = datetime(2022, 1, 21, 10, 0, tzinfo=UTC)
POLITICA = carregar_politica(POLITICAS_EXEMPLO / "demo.yaml")


def cenario(categoria="forca_bruta", recorrencia=50, **evidencias):
    evento = Evento(
        tenant_id="demo",
        origem="wazuh",
        categoria=categoria,
        ip_origem="203.0.113.7",
        ip_destino="10.0.1.5",
        ocorrido_em=T0,
        evidencias=evidencias or {"regra": {"descricao": "sshd: authentication failed."}},
    )
    decisao = Motor(POLITICA).avaliar(evento, Contexto(recorrencia_24h=recorrencia))
    incidente = Incidente(
        tenant_id="demo",
        origem="wazuh",
        categoria=categoria,
        ativo="servidor-pagamentos",
        aberto_em=T0,
        atualizado_em=T0 + timedelta(minutes=12),
        total_eventos=recorrencia,
        prioridade=decisao.prioridade,
    )
    return incidente, decisao, evento


def test_toda_categoria_tem_titulo_e_acao():
    assert set(TITULO) == set(Categoria) and set(ACAO) == set(Categoria)


def test_mensagem_do_incidente_tem_as_tres_partes_e_o_rastro():
    incidente, decisao, evento = cenario()
    texto = mensagem_incidente(incidente, decisao, evento)
    assert texto.startswith("🟠 P2 · Tentativas de senha (força bruta)")
    assert "servidor-pagamentos · resposta em 1 h" in texto
    assert "O que houve\n50 eventos de wazuh em 12 min" in texto
    assert "Último alerta: sshd: authentication failed." in texto
    assert "Por que P2\n" in texto
    # O rastro vira a explicação.
    assert "- recorrencia_24h >= 50 (só forca_bruta): urgência sobe para alta" in texto
    assert "Ação sugerida\nBloqueie o IP de origem" in texto


def test_assinatura_do_suricata_aparece_como_ultimo_alerta():
    incidente, decisao, evento = cenario(suricata={"assinatura": "ET SCAN Nmap"})
    assert "Último alerta: ET SCAN Nmap" in mensagem_incidente(incidente, decisao, evento)


def test_texto_enorme_e_cortado_no_limite_do_telegram():
    incidente, decisao, evento = cenario(regra={"descricao": "x" * 10_000})
    texto = mensagem_incidente(incidente, decisao, evento)
    assert tamanho_telegram(texto) <= LIMITE_TELEGRAM and texto.endswith("(mensagem cortada)")


def test_agrupada_e_resumo():
    incidente, _, _ = cenario()
    outro = incidente.model_copy(update={"ativo": "web", "total_eventos": 1})
    agrupada = mensagem_agrupada(
        "demo", "wazuh", Prioridade.P2, [incidente, outro], timedelta(minutes=10)
    )
    assert agrupada.startswith("🟠 2 incidentes P2 de wazuh nos últimos 10 min")
    assert "- Tentativas de senha (força bruta) · web · 1 evento\n" in agrupada
    resumo = resumo_diario("demo", T0, Prioridade.P3, [incidente, outro])
    assert (
        f"2 incidentes P3 desde o último resumo ({incidente.total_eventos + 1} eventos)" in resumo
    )
    assert "Tentativas de senha (força bruta): 2 incidentes em 2 ativos" in resumo
    assert "mais frequentes: servidor-pagamentos (1), web (1)" in resumo


def test_resumo_conta_por_categoria_em_vez_de_listar():
    """229 P3 num resumo não cabiam na mensagem (A4): o resumo agora só conta."""
    incidente, _, _ = cenario()
    muitos = [
        incidente.model_copy(update={"ativo": f"10.0.0.{i % 40}", "total_eventos": 2})
        for i in range(500)
    ]
    resumo = resumo_diario("demo", T0, Prioridade.P3, muitos)
    assert tamanho_telegram(resumo) < 1000
    assert "500 incidentes em 40 ativos, 1000 eventos" in resumo
    assert resumo.count("10.0.0.") == 3  # só os mais frequentes
