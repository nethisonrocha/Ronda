import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

from tests.conftest import RAIZ

_spec = importlib.util.spec_from_file_location(
    "download_data", RAIZ / "scripts" / "download_data.py"
)
download_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download_data)


def test_manifesto_do_repositorio_e_valido():
    datasets = download_data.carregar_manifesto()
    assert {"ait-ads", "cic-ids2017", "cic-ids2017-improved", "netflow-v3", "bccc"} <= set(datasets)


def _zip(tmp_path: Path, membros: dict[str, str]) -> tuple[str, str]:
    origem = tmp_path / "origem.zip"
    with zipfile.ZipFile(origem, "w") as z:
        for nome, conteudo in membros.items():
            z.writestr(nome, conteudo)
    return origem.as_uri(), hashlib.sha256(origem.read_bytes()).hexdigest()


def _ds(url: str, sha: str | None) -> dict:
    return {
        "download": "automatico",
        "pagina": "https://exemplo.org",
        "arquivos": [{"url": url, "nome": "pacote.zip", "sha256": sha, "descompactar": True}],
    }


def test_baixa_confere_e_descompacta(tmp_path):
    url, sha = _zip(tmp_path, {"fluxos.csv": "a,b\n1,2\n"})
    data = tmp_path / "data"

    assert download_data.obter_dataset("teste", _ds(url, sha), data) == []
    assert (data / "raw" / "teste" / "fluxos.csv").read_text() == "a,b\n1,2\n"
    # Rodar de novo não baixa nem extrai outra vez.
    assert download_data.obter_dataset("teste", _ds(url, sha), data) == []


def test_checksum_divergente_para_tudo(tmp_path):
    url, _ = _zip(tmp_path, {"fluxos.csv": "x"})
    with pytest.raises(download_data.ErroDownload, match="checksum"):
        download_data.obter_dataset("teste", _ds(url, "0" * 64), tmp_path / "data")


def test_sem_checksum_no_manifesto_avisa_o_valor_calculado(tmp_path):
    url, sha = _zip(tmp_path, {"fluxos.csv": "x"})
    avisos = download_data.obter_dataset("teste", _ds(url, None), tmp_path / "data")
    assert any(sha in aviso for aviso in avisos)


def test_zip_com_caminho_que_escapa_da_pasta_e_recusado(tmp_path):
    url, sha = _zip(tmp_path, {"../../fora.txt": "x"})
    with pytest.raises(download_data.ErroDownload, match="inseguro"):
        download_data.obter_dataset("teste", _ds(url, sha), tmp_path / "data")
    assert not (tmp_path / "data" / "fora.txt").exists()


def test_dataset_manual_so_orienta(tmp_path):
    ds = _ds("https://exemplo.org/x.zip", None) | {"download": "manual"}
    avisos = download_data.obter_dataset("teste", ds, tmp_path / "data")
    assert "manualmente" in avisos[0]
