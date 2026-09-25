from ronda.domain.priority import Criticidade, Impacto, Prioridade, Urgencia
from ronda.domain.taxonomy import PRIORIDADE_BASE, Categoria


def test_deslocar_sobe_e_desce_na_escala():
    assert Urgencia.baixa.deslocar(1) is Urgencia.media
    assert Urgencia.media.deslocar(1) is Urgencia.alta
    assert Impacto.alto.deslocar(-2) is Impacto.baixo


def test_deslocar_para_nas_pontas():
    assert Urgencia.alta.deslocar(1) is Urgencia.alta
    assert Criticidade.baixa.deslocar(-3) is Criticidade.baixa


def test_nivel_da_prioridade():
    assert [p.nivel for p in Prioridade] == [1, 2, 3, 4]


def test_toda_categoria_tem_prioridade_base():
    assert set(PRIORIDADE_BASE) == set(Categoria)
