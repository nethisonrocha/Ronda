"""Testes de integração no PostgreSQL real para RepositorioMetricas e /v1/incidentes."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ronda.api.deps import banco_de_dados
from ronda.api.main import app
from ronda.domain.incident import EstadoIncidente
from ronda.domain.priority import Criticidade, Impacto, Prioridade, Urgencia
from ronda.governance.engine import Decisao
from ronda.governance.trace import Passo, Rastro
from ronda.storage.repositories import (
    RepositorioAuditoria,
    RepositorioDecisoes,
    RepositorioEventos,
    RepositorioIncidentes,
    RepositorioMetricas,
    RepositorioTokens,
)


@pytest.fixture
def cliente(banco):
    app.dependency_overrides[banco_de_dados] = lambda: banco
    yield TestClient(app)
    app.dependency_overrides.clear()


def _decisao_p1() -> Decisao:
    return Decisao(
        prioridade=Prioridade.P1,
        impacto=Impacto.alto,
        urgencia=Urgencia.alta,
        ativo="servidor-pagamentos",
        criticidade=Criticidade.alta,
        resposta=timedelta(minutes=15),
        politica_versao=4,
        prioridade_base=False,
        rastro=Rastro(
            passos=[
                Passo(etapa="categoria", texto="negacao_servico"),
                Passo(etapa="prioridade", texto="P1, resposta em 15 min"),
            ]
        ),
    )


def test_repositorio_metricas_calcula_agregacoes_e_isolamento_rls(banco, incidente, evento):
    inc1 = incidente(prioridade=Prioridade.P1)
    inc2 = incidente(
        ativo="servidor-web",
        prioridade=Prioridade.P3,
    )
    ev1 = evento(ocorrido_em=inc1.aberto_em)
    ev2 = evento(ocorrido_em=inc1.aberto_em + timedelta(seconds=10))
    ev3 = evento(ocorrido_em=inc1.aberto_em + timedelta(seconds=20))

    with banco.sessao("demo") as sessao:
        ri = RepositorioIncidentes(sessao)
        re = RepositorioEventos(sessao)
        ri.abrir(inc1)
        ri.abrir(inc2)
        ri.reconhecer(inc2.id, inc2.aberto_em + timedelta(seconds=60))
        for ev in (ev1, ev2, ev3):
            re.registrar(ev)
        ri.vincular_evento(inc1.id, ev1.id)
        ri.vincular_evento(inc1.id, ev2.id)
        ri.vincular_evento(inc2.id, ev3.id)

    # Outro tenant não interfere nas métricas de demo.
    inc_acme = incidente(tenant_id="acme", prioridade=Prioridade.P2)
    ev_acme = evento(tenant_id="acme")
    with banco.sessao("acme") as sessao:
        RepositorioIncidentes(sessao).abrir(inc_acme)
        RepositorioEventos(sessao).registrar(ev_acme)

    with banco.sessao("demo") as sessao:
        resumo = RepositorioMetricas(sessao).resumo()
        assert resumo.total_eventos == 3
        assert resumo.total_incidentes == 2
        assert resumo.incidentes_por_prioridade == {"P1": 1, "P2": 0, "P3": 1, "P4": 0}
        assert resumo.incidentes_por_estado == {"aberto": 1, "reconhecido": 1, "resolvido": 0}
        assert resumo.taxa_reducao_eventos == round(1.0 - 2 / 3, 4)
        assert resumo.tempo_medio_reconhecimento_s == 60.0

    with banco.sessao("acme") as sessao:
        resumo_acme = RepositorioMetricas(sessao).resumo()
        assert resumo_acme.total_eventos == 1
        assert resumo_acme.total_incidentes == 1
        assert resumo_acme.tempo_medio_reconhecimento_s is None


def test_rotas_incidentes_e_metricas_com_postgres_real(banco, cliente, incidente, evento):
    inc = incidente(prioridade=Prioridade.P1)
    ev = evento(ocorrido_em=inc.aberto_em)
    with banco.sessao("demo") as sessao:
        token_demo, _ = RepositorioTokens(sessao).criar("painel-demo")
        RepositorioIncidentes(sessao).abrir(inc)
        RepositorioEventos(sessao).registrar(ev)
        RepositorioIncidentes(sessao).vincular_evento(inc.id, ev.id)
        RepositorioDecisoes(sessao).registrar(_decisao_p1(), evento_id=ev.id, incidente_id=inc.id)

    with banco.sessao("acme") as sessao:
        token_acme, _ = RepositorioTokens(sessao).criar("painel-acme")

    hdr_demo = {"Authorization": f"Bearer {token_demo}"}
    hdr_acme = {"Authorization": f"Bearer {token_acme}"}

    # Listagem filtrada em demo vs isolamento em acme.
    lista = cliente.get(
        "/v1/incidentes?prioridade=P1&categoria=negacao_servico&ativo=servidor-pagamentos",
        headers=hdr_demo,
    )
    assert lista.status_code == 200
    assert [i["id"] for i in lista.json()] == [str(inc.id)]
    assert cliente.get("/v1/incidentes", headers=hdr_acme).json() == []

    # Detalhe com rastro e eventos.
    detalhe = cliente.get(f"/v1/incidentes/{inc.id}", headers=hdr_demo)
    assert detalhe.status_code == 200
    corpo = detalhe.json()
    assert corpo["incidente"]["id"] == str(inc.id)
    assert len(corpo["decisoes"]) == 1
    assert corpo["decisoes"][0]["decisao"]["rastro"]["passos"][0]["etapa"] == "categoria"
    assert [e["id"] for e in corpo["eventos"]] == [str(ev.id)]

    # Outro tenant recebe 404.
    assert cliente.get(f"/v1/incidentes/{inc.id}", headers=hdr_acme).status_code == 404
    assert cliente.get(f"/v1/incidentes/{uuid4()}", headers=hdr_demo).status_code == 404

    # Reconhecimento via API grava auditoria e é idempotente.
    rec1 = cliente.post(f"/v1/incidentes/{inc.id}/reconhecer", headers=hdr_demo)
    assert rec1.status_code == 200
    assert rec1.json()["reconhecido"] is True
    assert rec1.json()["incidente"]["estado"] == EstadoIncidente.reconhecido.value

    rec2 = cliente.post(f"/v1/incidentes/{inc.id}/reconhecer", headers=hdr_demo)
    assert rec2.status_code == 200
    assert rec2.json()["reconhecido"] is False

    with banco.sessao("demo") as sessao:
        trilha = RepositorioAuditoria(sessao).listar(entidade="incidente", entidade_id=inc.id)
        assert [a.acao for a in trilha] == ["incidente.reconhecido"]

    # Métricas via API.
    resumo = cliente.get("/v1/metricas/resumo", headers=hdr_demo)
    assert resumo.status_code == 200
    assert resumo.json()["total_incidentes"] == 1
    assert resumo.json()["incidentes_por_estado"]["reconhecido"] == 1
    assert resumo.json()["tempo_medio_reconhecimento_s"] is not None
