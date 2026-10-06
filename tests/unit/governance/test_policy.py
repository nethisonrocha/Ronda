import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ronda.domain.incident import Contexto
from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria
from ronda.governance.policy import (
    Condicao,
    PoliticaInvalida,
    PoliticaNaoEncontrada,
    RepositorioPoliticas,
    ler_politica,
)

MATRIZ = {
    "alto": {"alta": "P1", "media": "P2", "baixa": "P3"},
    "medio": {"alta": "P2", "media": "P3", "baixa": "P4"},
    "baixo": {"alta": "P3", "media": "P4", "baixa": "P4"},
}


def minima(**extra):
    return {"tenant": "acme", "versao": 1, "matriz": MATRIZ} | extra


def test_politica_de_exemplo_e_valida(politica_demo):
    assert politica_demo.tenant == "demo"
    assert politica_demo.versao == 4
    assert politica_demo.resposta[Prioridade.P1] == timedelta(minutes=15)
    assert Prioridade.P4 not in politica_demo.resposta


def test_duracoes():
    politica = ler_politica(minima(resposta={"P1": "15min", "P2": "1h", "P3": "2d"}))
    assert politica.resposta == {
        Prioridade.P1: timedelta(minutes=15),
        Prioridade.P2: timedelta(hours=1),
        Prioridade.P3: timedelta(days=2),
    }


@pytest.mark.parametrize(
    ("dados", "trecho"),
    [
        (minima(resposta={"P1": "15 minutos"}), "duração inválida"),
        (
            minima(matriz={k: v for k, v in MATRIZ.items() if k != "baixo"}),
            "linha de impacto baixo",
        ),
        (minima(matriz=MATRIZ | {"medio": {"alta": "P2"}}), "falta urgência"),
        (minima(impacto={"forca_bruta": {"alta": "medio"}}), "falta criticidade"),
        (minima(impacto={"phishing": {"alta": "alto"}}), "phishing"),
        (minima(ativos=[{"nome": "a", "criticidade": "alta"}] * 2), "mais de uma vez"),
        (minima(ativos=[{"nome": "a", "rede": "10.0.0.1/24", "criticidade": "alta"}]), "rede"),
        (
            minima(urgencia={"modificadores": [{"se": "hora > 22", "subir": 1}]}),
            "campo desconhecido",
        ),
        (minima(urgencia={"modificadores": [{"se": "confirmado"}]}), "subir e descer"),
        (minima(campo_que_nao_existe=1), "campo_que_nao_existe"),
    ],
)
def test_politica_invalida_explica_o_motivo(dados, trecho):
    with pytest.raises(PoliticaInvalida, match=trecho):
        ler_politica(dados)


@pytest.mark.parametrize(
    ("texto", "contexto", "esperado"),
    [
        ("recorrencia_24h >= 5", Contexto(recorrencia_24h=5), True),
        ("recorrencia_24h >= 5", Contexto(recorrencia_24h=4), False),
        ("confirmado", Contexto(confirmado=True), True),
        ("confirmado", Contexto(), False),
        ("fora_do_horario == false", Contexto(), True),
        ("recorrencia_24h", Contexto(recorrencia_24h=1), True),
    ],
)
def test_condicoes(texto, contexto, esperado):
    assert Condicao(texto).avaliar(contexto) is esperado


@pytest.mark.parametrize(
    "texto", ["confirmado >= 1", "recorrencia_24h >= muito", "__import__('os')", "a and b"]
)
def test_condicao_rejeita_o_que_nao_e_comparacao_simples(texto):
    with pytest.raises(ValueError):
        Condicao(texto)


def test_repositorio_le_por_tenant_e_recarrega_quando_o_arquivo_muda(tmp_path: Path):
    arquivo = tmp_path / "acme.yaml"
    arquivo.write_text("tenant: acme\nversao: 1\nmatriz: " + repr(MATRIZ), encoding="utf-8")
    repositorio = RepositorioPoliticas(tmp_path)
    assert repositorio.obter("acme").versao == 1
    assert repositorio.obter("acme") is repositorio.obter("acme")

    arquivo.write_text("tenant: acme\nversao: 2\nmatriz: " + repr(MATRIZ), encoding="utf-8")
    os.utime(arquivo, ns=(0, arquivo.stat().st_mtime_ns + 1_000_000))
    assert repositorio.obter("acme").versao == 2


def test_repositorio_recusa_tenant_invalido_ou_ausente(tmp_path: Path):
    repositorio = RepositorioPoliticas(tmp_path)
    for tenant in ("../segredo", "ACME", "nao-existe"):
        with pytest.raises(PoliticaNaoEncontrada):
            repositorio.obter(tenant)


def test_repositorio_recusa_arquivo_de_outro_tenant(tmp_path: Path):
    (tmp_path / "acme.yaml").write_text(
        "tenant: outro\nversao: 1\nmatriz: " + repr(MATRIZ), encoding="utf-8"
    )
    with pytest.raises(PoliticaInvalida, match="esperado 'acme'"):
        RepositorioPoliticas(tmp_path).obter("acme")


# --- decisões do dono de 06/10/2026 (A1, A3, A5) ---------------------------------------


def test_modificador_por_categoria_e_com_excecao():
    politica = ler_politica(
        minima(
            urgencia={
                "modificadores": [
                    {"se": "recorrencia_24h >= 5", "subir": 1, "exceto": ["forca_bruta"]},
                    {"se": "recorrencia_24h >= 50", "subir": 1, "categorias": ["forca_bruta"]},
                ]
            }
        )
    )
    geral, forca_bruta = politica.urgencia.modificadores
    contexto = Contexto(recorrencia_24h=10)
    assert geral.aplica(contexto, Categoria.ataque_web)
    assert not geral.aplica(contexto, Categoria.forca_bruta)
    assert not forca_bruta.aplica(contexto, Categoria.forca_bruta)  # 10 < 50
    assert forca_bruta.aplica(Contexto(recorrencia_24h=50), Categoria.forca_bruta)
    assert not forca_bruta.aplica(Contexto(recorrencia_24h=50), Categoria.ataque_web)
    assert forca_bruta.descricao == "recorrencia_24h >= 50 (só forca_bruta)"


def test_modificador_recusa_categorias_e_exceto_juntos():
    modificador = {"se": "confirmado", "subir": 1, "categorias": ["forca_bruta"]}
    with pytest.raises(PoliticaInvalida, match="categorias ou exceto"):
        ler_politica(minima(urgencia={"modificadores": [modificador | {"exceto": ["benigno"]}]}))


@pytest.mark.parametrize(
    ("instante_utc", "fora"),
    [
        (datetime(2026, 10, 5, 13, 0, tzinfo=UTC), False),  # segunda, 10:00 em Fortaleza
        (datetime(2026, 10, 5, 11, 0, tzinfo=UTC), False),  # segunda, 08:00: o início conta
        (datetime(2026, 10, 5, 21, 0, tzinfo=UTC), True),  # segunda, 18:00: o fim não conta
        (datetime(2026, 10, 6, 2, 0, tzinfo=UTC), True),  # segunda, 23:00
        (datetime(2026, 10, 10, 13, 0, tzinfo=UTC), True),  # sábado
    ],
)
def test_fora_do_expediente_no_fuso_do_tenant(instante_utc, fora):
    politica = ler_politica(minima(expediente={"fuso": "America/Fortaleza"}))
    assert politica.expediente.fora(instante_utc) is fora


def test_expediente_invalido():
    with pytest.raises(PoliticaInvalida, match="início precisa vir antes"):
        ler_politica(minima(expediente={"inicio": "18:00", "fim": "08:00"}))


def test_silencio_por_origem_precisa_ser_maior_que_a_janela():
    notificacao = {"destino_env": "CHAT", "silencio_por_origem": "30min"}
    with pytest.raises(PoliticaInvalida, match="nunca suprime"):
        ler_politica(minima(correlacao={"janela": "30min"}, notificacao=notificacao))
    valida = ler_politica(minima(notificacao=notificacao | {"silencio_por_origem": "2h"}))
    assert valida.notificacao.silencio_por_origem == timedelta(hours=2)


def test_politica_diz_que_campos_do_contexto_usa():
    politica = ler_politica(
        minima(urgencia={"modificadores": [{"se": "ataque_previo_no_ativo", "subir": 1}]})
    )
    assert politica.usa("ataque_previo_no_ativo")
    assert not politica.usa("fora_do_horario")
