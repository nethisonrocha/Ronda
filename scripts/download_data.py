"""Baixa os datasets do manifesto, confere o checksum e descompacta em data/raw/.

Uso:
    python scripts/download_data.py                 # todos
    python scripts/download_data.py --dataset ait-ads
    python scripts/download_data.py --list

Também é a primeira célula dos notebooks do Colab, para que todos obtenham os mesmos dados.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[1]
DATA = RAIZ / "data"
MANIFESTO = DATA / "datasets.yaml"
SUBPASTAS = [
    "raw",
    "interim",
    "processed/governance-eval",
    "processed/detector",
    "processed/translator",
]


class ErroDownload(RuntimeError):
    pass


def carregar_manifesto(caminho: Path = MANIFESTO) -> dict[str, dict[str, Any]]:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    datasets = dados.get("datasets")
    if not isinstance(datasets, dict):
        raise ErroDownload(f"{caminho}: falta a chave 'datasets'")
    for chave, ds in datasets.items():
        if ds.get("download") not in ("automatico", "manual"):
            raise ErroDownload(f"{chave}: download precisa ser 'automatico' ou 'manual'")
        for arquivo in ds.get("arquivos") or []:
            if not arquivo.get("nome") or "/" in arquivo["nome"] or "\\" in arquivo["nome"]:
                raise ErroDownload(f"{chave}: todo arquivo precisa de um nome simples")
    return datasets


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(url: str, destino: Path) -> None:
    parcial = destino.with_name(destino.name + ".part")
    with urllib.request.urlopen(url) as resposta, parcial.open("wb") as saida:
        shutil.copyfileobj(resposta, saida, length=1 << 20)
    parcial.replace(destino)


def _dentro(base: Path, alvo: Path) -> bool:
    return alvo.resolve().is_relative_to(base.resolve())


def descompactar(arquivo: Path, destino: Path) -> None:
    """Extrai recusando caminhos que escapem de destino (zip slip)."""
    if zipfile.is_zipfile(arquivo):
        with zipfile.ZipFile(arquivo) as z:
            for membro in z.namelist():
                if not _dentro(destino, destino / membro):
                    raise ErroDownload(f"{arquivo.name}: caminho inseguro {membro!r}")
            z.extractall(destino)
    elif tarfile.is_tarfile(arquivo):
        with tarfile.open(arquivo) as t:
            t.extractall(destino, filter="data")
    else:
        raise ErroDownload(f"{arquivo.name}: formato não reconhecido para descompactar")


def obter_dataset(chave: str, ds: dict[str, Any], data: Path = DATA) -> list[str]:
    """Garante os arquivos do dataset em data/raw/<chave>/. Devolve avisos."""
    avisos: list[str] = []
    pasta = data / "raw" / chave
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = ds.get("arquivos") or []

    if not arquivos:
        return [f"{chave}: nenhum arquivo no manifesto ainda (página: {ds.get('pagina')})"]

    for arquivo in arquivos:
        destino = pasta / arquivo["nome"]
        esperado = arquivo.get("sha256")

        if not destino.exists():
            if ds["download"] == "manual" or not arquivo.get("url"):
                avisos.append(
                    f"{chave}: baixe {arquivo['nome']} manualmente em {ds.get('pagina')} "
                    f"e coloque em {destino.relative_to(data.parent)}"
                )
                continue
            print(f"{chave}: baixando {arquivo['nome']}…")
            baixar(arquivo["url"], destino)

        calculado = sha256(destino)
        if esperado is None:
            avisos.append(
                f"{chave}: {arquivo['nome']} sem sha256 no manifesto; calculado {calculado}"
            )
        elif calculado != esperado.lower():
            raise ErroDownload(
                f"{chave}: checksum de {arquivo['nome']} não confere "
                f"(esperado {esperado}, obtido {calculado}); apague o arquivo e baixe de novo"
            )

        marcador = pasta / f".{arquivo['nome']}.extraido"
        if arquivo.get("descompactar") and not marcador.exists():
            print(f"{chave}: descompactando {arquivo['nome']}…")
            descompactar(destino, pasta)
            marcador.write_text(calculado, encoding="utf-8")
    return avisos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", help="baixa só este dataset (chave do manifesto)")
    parser.add_argument("--list", action="store_true", help="lista os datasets e sai")
    args = parser.parse_args(argv)

    datasets = carregar_manifesto()
    if args.list:
        for chave, ds in datasets.items():
            print(f"{chave:24} {ds['download']:11} {len(ds.get('arquivos') or [])} arquivo(s)")
        return 0

    if args.dataset and args.dataset not in datasets:
        print(f"dataset desconhecido: {args.dataset}; opções: {', '.join(datasets)}")
        return 2

    for sub in SUBPASTAS:
        (DATA / sub).mkdir(parents=True, exist_ok=True)

    escolhidos = {args.dataset: datasets[args.dataset]} if args.dataset else datasets
    avisos: list[str] = []
    try:
        for chave, ds in escolhidos.items():
            avisos += obter_dataset(chave, ds)
    except ErroDownload as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    for aviso in avisos:
        print(f"aviso: {aviso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
