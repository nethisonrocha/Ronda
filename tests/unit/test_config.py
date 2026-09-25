import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from ronda.config import Configuracao, mascarar

SENHA = "s3gr3d0-n40-vaza"


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    """Nenhum teste enxerga as variáveis RONDA_* nem o .env da máquina."""
    for nome in list(os.environ):
        if nome.upper().startswith("RONDA_"):
            monkeypatch.delenv(nome)


def configurar(**kwargs) -> Configuracao:
    return Configuracao(_env_file=None, **kwargs)


def test_padroes_sem_nada_configurado():
    cfg = configurar()
    assert cfg.ambiente == "desenvolvimento"
    assert cfg.diretorio_politicas == Path("policies/examples")
    assert cfg.url_banco is None and cfg.url_redis is None


def test_le_variaveis_de_ambiente(monkeypatch):
    monkeypatch.setenv("RONDA_ENV", "teste")
    monkeypatch.setenv("RONDA_POLICIES_DIR", "outro/lugar")
    monkeypatch.setenv(
        "RONDA_DATABASE_URL", f"postgresql+psycopg://ronda_app:{SENHA}@db:5432/ronda"
    )
    monkeypatch.setenv("RONDA_REDIS_URL", f"redis://:{SENHA}@cache:6379/0")

    cfg = configurar()

    assert cfg.ambiente == "teste"
    assert cfg.diretorio_politicas == Path("outro/lugar")
    assert cfg.url_banco.hosts()[0]["host"] == "db"
    assert cfg.url_redis.path == "/0"


def test_le_o_arquivo_env_e_ignora_variaveis_do_compose(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "RONDA_ENV=producao\n"
        f"RONDA_PG_PASSWORD={SENHA}\n"  # só do compose; não pode quebrar a leitura
        "RONDA_REDIS_URL=redis://127.0.0.1:6382/2\n",
        encoding="utf-8",
    )
    cfg = Configuracao(_env_file=arquivo)
    assert cfg.ambiente == "producao"
    assert str(cfg.url_redis) == "redis://127.0.0.1:6382/2"

    monkeypatch.setenv("RONDA_ENV", "teste")
    assert Configuracao(_env_file=arquivo).ambiente == "teste"  # ambiente vence o .env


def test_ambiente_desconhecido_e_recusado(monkeypatch):
    monkeypatch.setenv("RONDA_ENV", "staging")
    with pytest.raises(ValidationError):
        configurar()


def test_url_de_banco_com_esquema_errado_e_recusada_sem_mostrar_a_senha(monkeypatch):
    monkeypatch.setenv("RONDA_DATABASE_URL", f"mysql://root:{SENHA}@db/ronda")
    with pytest.raises(ValidationError) as erro:
        configurar()
    assert SENHA not in str(erro.value)


def test_senhas_nao_aparecem_no_repr_nem_no_resumo(monkeypatch):
    monkeypatch.setenv("RONDA_DATABASE_URL", f"postgresql://ronda_app:{SENHA}@db:5435/ronda")
    monkeypatch.setenv("RONDA_REDIS_URL", f"redis://:{SENHA}@cache:6382/0")
    cfg = configurar()

    assert SENHA not in repr(cfg)
    resumo = cfg.resumo()
    assert SENHA not in str(resumo)
    assert resumo["url_banco"] == "postgresql://ronda_app:***@db:5435/ronda"
    assert resumo["url_redis"] == "redis://:***@cache:6382/0"


def test_mascarar_url_sem_senha_fica_igual():
    assert mascarar(None) is None
    cfg = configurar(url_redis="redis://127.0.0.1:6382/0")
    assert mascarar(cfg.url_redis) == "redis://127.0.0.1:6382/0"


def test_configuracao_e_imutavel():
    cfg = configurar()
    with pytest.raises(ValidationError):
        cfg.ambiente = "producao"


def test_env_example_e_uma_configuracao_valida():
    """O .env.example versionado precisa carregar sem erro."""
    raiz = Path(__file__).resolve().parents[2]
    cfg = Configuracao(_env_file=raiz / ".env.example")
    assert cfg.url_banco is not None and cfg.url_banco_migracao is not None
    assert cfg.url_redis is not None
    assert cfg.url_banco.hosts()[0]["username"] == "ronda_app"
