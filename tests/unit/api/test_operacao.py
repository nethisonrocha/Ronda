"""Testes unitários das rotas de consulta/operação (/v1/incidentes, /v1/metricas) e CORS."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ronda.api.deps import banco_de_dados, repositorio_politicas, tenant_do_token
from ronda.api.main import app
from ronda.api.routes import incidentes as rota_incidentes
from ronda.api.routes import metricas as rota_metricas
from ronda.domain.event import Evento
from ronda.domain.incident import Contexto, EstadoIncidente, Incidente
from ronda.domain.priority import Criticidade, Impacto, Prioridade, Urgencia
from ronda.domain.taxonomy import Categoria
from ronda.governance.engine import Decisao
from ronda.governance.policy import RepositorioPoliticas
from ronda.governance.trace import Passo, Rastro
from ronda.storage.repositories import DecisaoRegistrada, ResumoMetricas
from tests.conftest import POLITICAS_EXEMPLO

AGORA = datetime(2026, 11, 23, 14, 0, tzinfo=UTC)
INC_ID = uuid4()
EV_ID = uuid4()


def _incidente(estado: EstadoIncidente = EstadoIncidente.aberto) -> Incidente:
    return Incidente(
        id=INC_ID,
        tenant_id="demo",
        origem="wazuh",
        categoria=Categoria.negacao_servico,
        ativo="servidor-pagamentos",
        estado=estado,
        prioridade=Prioridade.P1,
        total_eventos=3,
        contexto=Contexto(recorrencia_24h=3),
        aberto_em=AGORA,
        atualizado_em=AGORA,
        reconhecido_em=AGORA if estado == EstadoIncidente.reconhecido else None,
    )


class _BancoFalso:
    @contextmanager
    def sessao(self, tenant_id: str):
        yield tenant_id


@pytest.fixture
def estado_falso(monkeypatch):
    estado = {
        "incidente": _incidente(),
        "auditoria": [],
        "filtros_chamados": None,
    }

    class _RepoIncFalso:
        def __init__(self, _sessao):
            pass

        def listar(self, **kwargs):
            estado["filtros_chamados"] = kwargs
            inc = estado["incidente"]
            if kwargs.get("prioridade") and inc.prioridade != kwargs["prioridade"]:
                return []
            return [inc]

        def obter(self, inc_id):
            return estado["incidente"] if inc_id == INC_ID else None

        def reconhecer(self, inc_id, quando):
            if inc_id != INC_ID or estado["incidente"].estado != EstadoIncidente.aberto:
                return False
            estado["incidente"] = _incidente(EstadoIncidente.reconhecido)
            return True

    class _RepoDecFalso:
        def __init__(self, _sessao):
            pass

        def do_incidente(self, inc_id):
            decisao = Decisao(
                prioridade=Prioridade.P1,
                impacto=Impacto.alto,
                urgencia=Urgencia.alta,
                ativo="servidor-pagamentos",
                criticidade=Criticidade.alta,
                resposta=None,
                politica_versao=4,
                prioridade_base=False,
                rastro=Rastro(passos=[Passo(etapa="prioridade", texto="P1")]),
            )
            return [
                DecisaoRegistrada(
                    id=uuid4(),
                    tenant_id="demo",
                    evento_id=EV_ID,
                    incidente_id=inc_id,
                    decidido_em=AGORA,
                    decisao=decisao,
                )
            ]

    class _RepoEvFalso:
        def __init__(self, _sessao):
            pass

        def do_incidente(self, _inc_id, limite=100):
            return [
                Evento(
                    id=EV_ID,
                    tenant_id="demo",
                    origem="wazuh",
                    categoria=Categoria.negacao_servico,
                    ocorrido_em=AGORA,
                )
            ]

    class _RepoAudFalso:
        def __init__(self, _sessao):
            pass

        def registrar(self, ator, acao, entidade, entidade_id=None, dados=None):
            estado["auditoria"].append((ator, acao, entidade, entidade_id))

    class _RepoMetFalso:
        def __init__(self, _sessao):
            pass

        def resumo(self):
            return ResumoMetricas(
                total_eventos=100,
                total_incidentes=4,
                incidentes_por_prioridade={"P1": 1, "P2": 1, "P3": 1, "P4": 1},
                incidentes_por_estado={"aberto": 3, "reconhecido": 1, "resolvido": 0},
                notificacoes_por_estado={"pendente": 0, "enviada": 2, "suprimida": 1, "falhou": 0},
                taxa_reducao_eventos=0.96,
                tempo_medio_reconhecimento_s=45.0,
            )

    monkeypatch.setattr(rota_incidentes, "RepositorioIncidentes", _RepoIncFalso)
    monkeypatch.setattr(rota_incidentes, "RepositorioDecisoes", _RepoDecFalso)
    monkeypatch.setattr(rota_incidentes, "RepositorioEventos", _RepoEvFalso)
    monkeypatch.setattr(rota_incidentes, "RepositorioAuditoria", _RepoAudFalso)
    monkeypatch.setattr(rota_metricas, "RepositorioMetricas", _RepoMetFalso)
    return estado


@pytest.fixture
def cliente(estado_falso):
    app.dependency_overrides[tenant_do_token] = lambda: "demo"
    app.dependency_overrides[banco_de_dados] = lambda: _BancoFalso()
    app.dependency_overrides[repositorio_politicas] = lambda: RepositorioPoliticas(
        POLITICAS_EXEMPLO
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_listar_incidentes_com_filtros(cliente, estado_falso):
    resp = cliente.get("/v1/incidentes?prioridade=P1&limite=20&deslocamento=5")
    assert resp.status_code == 200
    dados = resp.json()
    assert len(dados) == 1
    assert dados[0]["id"] == str(INC_ID)
    assert estado_falso["filtros_chamados"]["prioridade"] == Prioridade.P1
    assert estado_falso["filtros_chamados"]["limite"] == 20
    assert estado_falso["filtros_chamados"]["deslocamento"] == 5

    vazio = cliente.get("/v1/incidentes?prioridade=P4")
    assert vazio.status_code == 200
    assert vazio.json() == []


def test_obter_incidente_e_404(cliente):
    resp = cliente.get(f"/v1/incidentes/{INC_ID}")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["incidente"]["id"] == str(INC_ID)
    assert len(corpo["decisoes"]) == 1
    assert len(corpo["eventos"]) == 1

    nao_achado = cliente.get(f"/v1/incidentes/{uuid4()}")
    assert nao_achado.status_code == 404


def test_reconhecer_incidente_e_idempotencia(cliente, estado_falso):
    resp1 = cliente.post(f"/v1/incidentes/{INC_ID}/reconhecer")
    assert resp1.status_code == 200
    assert resp1.json()["reconhecido"] is True
    assert resp1.json()["incidente"]["estado"] == "reconhecido"
    assert len(estado_falso["auditoria"]) == 1

    # Segunda chamada já reconhecida devolve reconhecido=False e não duplica auditoria.
    resp2 = cliente.post(f"/v1/incidentes/{INC_ID}/reconhecer")
    assert resp2.status_code == 200
    assert resp2.json()["reconhecido"] is False
    assert len(estado_falso["auditoria"]) == 1

    assert cliente.post(f"/v1/incidentes/{uuid4()}/reconhecer").status_code == 404


def test_resumo_metricas(cliente):
    resp = cliente.get("/v1/metricas/resumo")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total_eventos"] == 100
    assert corpo["taxa_reducao_eventos"] == 0.96
    assert corpo["incidentes_por_prioridade"]["P4"] == 1


def test_aliases_v1_e_cors(cliente):
    resp = cliente.get("/v1/politicas/demo", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    av = cliente.post(
        "/v1/eventos/avaliar",
        json={
            "evento": {
                "tenant_id": "demo",
                "origem": "wazuh",
                "categoria": "negacao_servico",
                "ip_destino": "10.0.1.5",
                "ocorrido_em": "2026-09-25T14:03:11Z",
            }
        },
    )
    assert av.status_code == 200
    assert av.json()["prioridade"] == "P1"
