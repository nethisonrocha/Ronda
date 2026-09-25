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
    csv = datasets["ait-ads-csv"]["arquivos"][0]
    assert "5459b57d1cc3ad359172c851104f4e6ed5d595d0" in csv["url"]
    assert len(csv["conteudo"]) == 8


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


def _ds_com_conteudo(tmp_path: Path) -> dict:
    """Zip com prefixo alerts_csv/, como o do repositório do AIT."""
    membros = {"alerts_csv/": "", "alerts_csv/fox_alerts.txt": "a", "alerts_csv/shaw.txt": "b"}
    url, sha = _zip(tmp_path, membros)
    ds = _ds(url, sha) | {"pasta": "ait-ads/csv"}
    ds["arquivos"][0] |= {
        "extrair_de": "alerts_csv/",
        "conteudo": {
            "fox_alerts.txt": hashlib.sha256(b"a").hexdigest(),
            "shaw.txt": hashlib.sha256(b"b").hexdigest(),
        },
    }
    return ds


def test_extrai_sem_prefixo_na_pasta_indicada_e_confere_conteudo(tmp_path):
    data = tmp_path / "data"
    assert download_data.obter_dataset("ait-ads-csv", _ds_com_conteudo(tmp_path), data) == []
    pasta = data / "raw" / "ait-ads" / "csv"
    assert (pasta / "fox_alerts.txt").read_text() == "a"
    assert not (pasta / "alerts_csv").exists()


def test_conteudo_ja_presente_dispensa_o_download(tmp_path):
    ds = _ds_com_conteudo(tmp_path)
    ds["arquivos"][0]["url"] = "file:///nao/existe.zip"  # falharia se tentasse baixar
    pasta = tmp_path / "data" / "raw" / "ait-ads" / "csv"
    pasta.mkdir(parents=True)
    (pasta / "fox_alerts.txt").write_text("a")
    (pasta / "shaw.txt").write_text("b")
    assert download_data.obter_dataset("ait-ads-csv", ds, tmp_path / "data") == []


def test_conteudo_alterado_depois_de_extrair_e_detectado(tmp_path):
    ds = _ds_com_conteudo(tmp_path)
    data = tmp_path / "data"
    download_data.obter_dataset("ait-ads-csv", ds, data)
    (data / "raw" / "ait-ads" / "csv" / "shaw.txt").write_text("editado")
    with pytest.raises(download_data.ErroDownload, match=r"shaw\.txt"):
        download_data.obter_dataset("ait-ads-csv", ds, data)


def test_pasta_fora_de_raw_e_recusada(tmp_path):
    ds = _ds_com_conteudo(tmp_path) | {"pasta": "../../fora"}
    with pytest.raises(download_data.ErroDownload, match="fora de data/raw"):
        download_data.obter_dataset("x", ds, tmp_path / "data")


def test_dataset_manual_so_orienta(tmp_path):
    ds = _ds("https://exemplo.org/x.zip", None) | {"download": "manual"}
    avisos = download_data.obter_dataset("teste", ds, tmp_path / "data")
    assert "manualmente" in avisos[0]
