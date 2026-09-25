from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ronda.storage.repositories import RepositorioAuditoria


def test_registrar_e_listar_mais_recentes_primeiro(banco):
    politica, incidente = "demo.yaml", uuid4()
    with banco.sessao("demo") as sessao:
        auditoria = RepositorioAuditoria(sessao)
        primeira = auditoria.registrar(
            "cli:nethison", "politica.aplicada", "politica", politica, {"de": 2, "para": 3}
        )
        auditoria.registrar("telegram:ana", "incidente.reconhecido", "incidente", incidente)
        auditoria.registrar("motor", "incidente.priorizado", "incidente", incidente, {"p": "P1"})

    with banco.sessao("demo") as sessao:
        auditoria = RepositorioAuditoria(sessao)
        todas = auditoria.listar()
        do_incidente = auditoria.listar(entidade="incidente", entidade_id=incidente)

    assert primeira.id == 1 and primeira.dados == {"de": 2, "para": 3}
    assert primeira.ocorrido_em is not None
    assert [e.acao for e in todas] == [
        "incidente.priorizado",
        "incidente.reconhecido",
        "politica.aplicada",
    ]
    assert [e.ator for e in do_incidente] == ["motor", "telegram:ana"]


def test_auditoria_de_um_tenant_nao_aparece_no_outro(banco):
    with banco.sessao("demo") as sessao:
        RepositorioAuditoria(sessao).registrar("motor", "x", "incidente")
    with banco.sessao("acme") as sessao:
        assert RepositorioAuditoria(sessao).listar() == []


@pytest.mark.parametrize(
    "comando", ["UPDATE auditoria SET ator = 'outro'", "DELETE FROM auditoria"]
)
def test_auditoria_e_somente_insercao(banco, dono, comando):
    with banco.sessao("demo") as sessao:
        RepositorioAuditoria(sessao).registrar("motor", "x", "incidente")

    with pytest.raises(DBAPIError, match="somente inserção"), banco.sessao("demo") as sessao:
        sessao.execute(text(comando))
    with pytest.raises(DBAPIError, match="somente inserção"), dono.begin() as conexao:
        conexao.execute(text(comando))
