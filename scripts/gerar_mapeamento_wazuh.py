"""Gera src/ronda/adapters/wazuh/mapping.yaml a partir da taxonomia aprovada.

Uso:
    uv run python scripts/gerar_mapeamento_wazuh.py              # regrava o mapping.yaml
    uv run python scripts/gerar_mapeamento_wazuh.py --verificar  # falha se estiver desatualizado

O mapeamento tem duas camadas:

1. **Exatas**, uma entrada por regra do Wazuh e por assinatura do Suricata vista no AIT-ADS,
   com a categoria decidida em docs/taxonomia-rascunho.csv.
2. **Genéricas**, as regras da seção 4.3 de docs/exploracao-ait-ads.md: grupos do Wazuh, família
   ET e categoria do Suricata. Cobrem alertas que o AIT-ADS não mostrou.

O que não casar com nenhuma das duas vira `desconhecido` no adaptador.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
TAXONOMIA = RAIZ / "docs" / "taxonomia-rascunho.csv"
DESTINO = RAIZ / "src" / "ronda" / "adapters" / "wazuh" / "mapping.yaml"

# Regras genéricas: a taxonomia aprovada, seção 4.3. A ordem dos grupos importa.
GRUPOS_WAZUH = [
    ("sudo", "comprometimento"),
    ("su", "comprometimento"),
    ("authentication_failed", "forca_bruta"),
    ("authentication_failures", "forca_bruta"),
    ("invalid_login", "forca_bruta"),
    ("web_scan", "reconhecimento"),
    ("recon", "reconhecimento"),
    ("access_denied", "reconhecimento"),
    ("attack", "ataque_web"),
    ("authentication_success", "benigno"),
]
FAMILIAS_ET = {"SCAN": "reconhecimento", "POLICY": "benigno"}
CATEGORIAS_SURICATA = {
    "Generic Protocol Command Decode": "desconhecido",
    "Not Suspicious Traffic": "benigno",
    "Potentially Bad Traffic": "desconhecido",
    "Web Application Attack": "ataque_web",
}
# Cópias do fast.log que não aparecem no russellmitchell nem no fox.
DUPLICATAS_FORA_DA_TAXONOMIA = {"20161": "confirmada no JSON do harrison (25/09/2026)"}

CABECALHO = """\
# Mapeamento de alertas do Wazuh (e do Suricata lido pelo Wazuh) para as categorias do Ronda.
#
# GERADO por scripts/gerar_mapeamento_wazuh.py a partir de docs/taxonomia-rascunho.csv.
# Não edite à mão: mude a taxonomia (ou as regras genéricas no gerador) e gere de novo.
#
# Ordem de decisão no adaptador:
#   Wazuh:    descartar → wazuh.regras (exata) → wazuh.grupos (primeiro que casar)
#   Suricata: suricata.assinaturas (exata) → suricata.familias_et → suricata.categorias
#   Sem nenhuma correspondência: desconhecido.
#
# A taxonomia ainda é provisória (T6 em docs/pendencias.md).
"""


def ler_taxonomia(caminho: Path = TAXONOMIA) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def montar(linhas: list[dict[str, str]]) -> dict:
    regras: dict[str, str] = {}
    assinaturas: dict[str, str] = {}
    descartar: set[str] = set(DUPLICATAS_FORA_DA_TAXONOMIA)
    for linha in linhas:
        ferramenta, assinatura = linha["ferramenta"], linha["assinatura"]
        categoria, classificacao = linha["categoria_proposta"], linha["classificacao"]
        if ferramenta == "wazuh_fastlog" or classificacao == "duplicata":
            descartar.add(assinatura.split(" ", 1)[0])
        elif ferramenta == "wazuh":
            regras[assinatura.split(" ", 1)[0]] = categoria
        elif ferramenta == "suricata":
            assinaturas[assinatura] = categoria
        else:
            raise ValueError(f"ferramenta desconhecida na taxonomia: {ferramenta!r}")
    return {
        "versao": 1,
        "taxonomia": "provisoria",
        "descartar": {"regras_fastlog": sorted(descartar, key=int)},
        "wazuh": {
            "regras": dict(sorted(regras.items(), key=lambda item: int(item[0]))),
            "grupos": [{"grupo": g, "categoria": c} for g, c in GRUPOS_WAZUH],
        },
        "suricata": {
            "assinaturas": dict(sorted(assinaturas.items())),
            "familias_et": dict(sorted(FAMILIAS_ET.items())),
            "categorias": dict(sorted(CATEGORIAS_SURICATA.items())),
        },
    }


def gerar(caminho: Path = TAXONOMIA) -> str:
    corpo = yaml.safe_dump(
        montar(ler_taxonomia(caminho)), allow_unicode=True, sort_keys=False, width=100
    )
    return CABECALHO + "\n" + corpo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verificar", action="store_true", help="só confere, sem gravar")
    args = parser.parse_args(argv)

    conteudo = gerar()
    atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else None
    if args.verificar:
        if atual != conteudo:
            print(
                f"{DESTINO.relative_to(RAIZ)} está desatualizado; rode o gerador", file=sys.stderr
            )
            return 1
        print("mapeamento em dia")
        return 0
    DESTINO.write_text(conteudo, encoding="utf-8", newline="\n")
    print(f"gravado {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
