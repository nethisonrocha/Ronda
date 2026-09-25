import pytest

from ronda.domain.incident import Contexto
from ronda.domain.priority import Prioridade
from ronda.governance.simulate import simular


def test_simulacao_conta_so_o_que_muda(politica_demo, evento):
    # Versão 4: ambiente de testes passa a ser tão crítico quanto pagamentos.
    dados = politica_demo.model_dump(mode="json")
    dados["versao"] = 4
    for ativo in dados["ativos"]:
        if ativo["nome"] == "ambiente-testes":
            ativo["criticidade"] = "alta"
    nova = type(politica_demo).model_validate(dados)

    itens = [
        (evento(ip_destino="10.0.9.20"), Contexto()),  # DoS em testes: P3 → P1
        (evento(ip_destino="10.0.9.21"), Contexto()),  # idem
        (evento(ip_destino="10.0.1.5"), Contexto()),  # pagamentos: continua P1
        (evento(categoria="benigno", ip_destino="10.0.9.20"), Contexto()),  # continua P4
    ]
    resultado = simular(itens, politica_demo, nova)

    assert (resultado.versao_atual, resultado.versao_nova) == (3, 4)
    assert resultado.total == 4
    assert resultado.transicoes == {"P3→P1": 2}
    assert [m.evento_id for m in resultado.mudancas] == [itens[0][0].id, itens[1][0].id]
    assert resultado.mudancas[0].de is Prioridade.P3
    assert "criticidade alta" in resultado.mudancas[0].rastro_novo


def test_simulacao_exige_mesmo_tenant(politica_demo):
    outra = politica_demo.model_copy(update={"tenant": "acme"})
    with pytest.raises(ValueError, match="mesmo tenant"):
        simular([], politica_demo, outra)
