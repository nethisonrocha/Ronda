"""Mede a cobertura do mapeamento do Wazuh nos cenários do AIT-ADS.

Uso:
    uv run python scripts/cobertura_mapeamento.py
    uv run python scripts/cobertura_mapeamento.py --cenarios fox santos --saida relatorio.md

Cada alerta de data/raw/ait-ads/json/<cenario>_wazuh.json passa pelo AdaptadorWazuh real, lido
linha a linha. Quando o CSV rotulado existe (data/raw/ait-ads/csv), o rótulo de cada alerta é
acoplado pela posição (o CSV sem o AMiner segue a ordem do JSON; cada linha é conferida) e o
script mede também o acerto da categoria nos alertas causados por ataque.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ronda.adapters.base import AlertaInvalido
from ronda.adapters.wazuh import AdaptadorWazuh, iterar_jsonl
from ronda.adapters.wazuh.adapter import desembrulhar
from ronda.domain.taxonomy import Categoria

RAIZ = Path(__file__).resolve().parents[1]
AIT = RAIZ / "data" / "raw" / "ait-ads"
CENARIOS = [
    "fox",
    "harrison",
    "russellmitchell",
    "santos",
    "shaw",
    "wardbeck",
    "wheeler",
    "wilson",
]
SAIDA_PADRAO = RAIZ / "docs" / "evaluation" / "cobertura-mapeamento-wazuh.md"

# Categoria esperada para cada rótulo de evento do AIT-ADS (event_label).
ESPERADO_POR_ROTULO = {
    "dirb": Categoria.reconhecimento,
    "wpscan": Categoria.reconhecimento,
    "service_scan": Categoria.reconhecimento,
    "dns_scan": Categoria.reconhecimento,
    "webshell_cmd": Categoria.ataque_web,
    "online_cracking": Categoria.forca_bruta,
    "crack_passwords": Categoria.forca_bruta,
    "escalated_sudo_command": Categoria.comprometimento,
    "attacker_change_user": Categoria.comprometimento,
    "dnsteal": Categoria.exfiltracao,
}


@dataclass
class Assinatura:
    categoria: str
    via: str
    chave: str
    grupos_ou_categoria: str
    alertas: Counter = field(default_factory=Counter)  # por cenário
    ataque: int = 0


@dataclass
class Cenario:
    nome: str
    alertas: int = 0
    descartados: int = 0
    invalidos: int = 0
    vias: Counter = field(default_factory=Counter)
    categorias: Counter = field(default_factory=Counter)
    desconhecido: int = 0
    rotulos_ok: bool | None = None  # None = sem CSV
    segundos: float = 0.0

    @property
    def eventos(self) -> int:
        return sum(self.vias.values())


def _leitor_de_rotulos(cenario: str):
    """Linhas W/S do CSV rotulado, na ordem do JSON; None se o CSV não existir."""
    caminho = AIT / "csv" / f"{cenario}_alerts.txt"
    if not caminho.exists():
        return None

    def linhas():
        with caminho.open(encoding="utf-8", newline="") as f:
            for linha in csv.DictReader(f):
                if not linha["short"].startswith("A"):
                    yield linha

    return linhas()


def _nome_no_csv(alerta: dict) -> str:
    descricao = str(alerta["rule"]["description"])
    return descricao if descricao.startswith("Suricata:") else f"Wazuh: {descricao}"


def medir(cenario: str, adaptador: AdaptadorWazuh, assinaturas: dict, acertos: dict) -> Cenario:
    resultado = Cenario(cenario)
    rotulos = _leitor_de_rotulos(cenario)
    resultado.rotulos_ok = None if rotulos is None else True
    inicio = time.perf_counter()
    for alerta in iterar_jsonl(AIT / "json" / f"{cenario}_wazuh.json"):
        resultado.alertas += 1
        rotulo = None
        if resultado.rotulos_ok:
            linha = next(rotulos, None)
            origem = desembrulhar(alerta)
            if linha is None or linha["name"] != _nome_no_csv(origem):
                resultado.rotulos_ok = False  # a junção posicional não vale; segue sem rótulos
            else:
                rotulo = linha["event_label"]
        try:
            evento = adaptador.converter_um(alerta, "ait-ads")
        except AlertaInvalido:
            resultado.invalidos += 1
            continue
        if evento is None:
            resultado.descartados += 1
            continue

        mapeamento = evento.evidencias["mapeamento"]
        via, categoria = mapeamento["via"], evento.categoria
        resultado.vias[via] += 1
        resultado.categorias[categoria.value] += 1
        if categoria is Categoria.desconhecido:
            resultado.desconhecido += 1

        if evento.origem == "suricata":
            chave_assinatura = f"suricata · {evento.evidencias['suricata']['assinatura']}"
            grupos = str(evento.evidencias["suricata"]["categoria"])
        else:
            regra = evento.evidencias["regra"]
            chave_assinatura = f"wazuh · {regra['id']} {regra['descricao']}"
            grupos = ", ".join(regra["grupos"])
        registro = assinaturas.get(chave_assinatura)
        if registro is None:
            registro = assinaturas[chave_assinatura] = Assinatura(
                categoria.value, via, mapeamento["chave"], grupos
            )
        registro.alertas[cenario] += 1

        if rotulo and rotulo != "-":
            registro.ataque += 1
            esperado = ESPERADO_POR_ROTULO.get(rotulo)
            acertos[rotulo]["eventos"] += 1
            acertos[rotulo]["obtidas"][categoria.value] += 1
            if esperado is not None and categoria is esperado:
                acertos[rotulo]["acertos"] += 1
    resultado.segundos = time.perf_counter() - inicio
    return resultado


def _pct(parte: int, todo: int) -> str:
    """Truncado, não arredondado: 15 alertas sem mapeamento em 2 milhões não viram 100%."""
    if todo == 0:
        return "—"
    return f"{math.floor(10_000 * parte / todo) / 100:.2f}%"


def _n(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def relatorio(cenarios: list[Cenario], assinaturas: dict, acertos: dict) -> str:
    linhas: list[str] = []
    add = linhas.append
    add("# Cobertura do mapeamento do Wazuh no AIT-ADS\n")
    add(
        "Gerado por `scripts/cobertura_mapeamento.py` com o `mapping.yaml` atual "
        "(taxonomia aprovada em 06/10/2026). Cada alerta passou pelo `AdaptadorWazuh`.\n"
    )
    add("- **exata**: regra ou assinatura listada na taxonomia;")
    add("- **genérica**: grupo do Wazuh, família ET ou categoria do Suricata;")
    add("- **sem mapeamento**: nada casou; vira `desconhecido`;")
    add(
        "- **cobertura** = (exata + genérica) / eventos; **categoria útil** = eventos "
        "que não terminaram em `desconhecido` (inclui os mapeados para `desconhecido` "
        "de propósito, como as anomalias de protocolo).\n"
    )

    add("## Por cenário\n")
    add(
        "| Cenário | Alertas | Descartados (fast.log) | Inválidos | Eventos | Exata | Genérica "
        "| Sem mapeamento | Cobertura | Categoria útil |"
    )
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    total = Cenario("**Total**")
    for c in cenarios:
        mapeados = c.vias["exata"] + c.vias["generica"]
        add(
            f"| {c.nome} | {_n(c.alertas)} | {_n(c.descartados)} | {_n(c.invalidos)} "
            f"| {_n(c.eventos)} | {_n(c.vias['exata'])} | {_n(c.vias['generica'])} "
            f"| {_n(c.vias['sem_mapeamento'])} | {_pct(mapeados, c.eventos)} "
            f"| {_pct(c.eventos - c.desconhecido, c.eventos)} |"
        )
        total.alertas += c.alertas
        total.descartados += c.descartados
        total.invalidos += c.invalidos
        total.vias.update(c.vias)
        total.categorias.update(c.categorias)
        total.desconhecido += c.desconhecido
    mapeados = total.vias["exata"] + total.vias["generica"]
    add(
        f"| **Total** | **{_n(total.alertas)}** | **{_n(total.descartados)}** "
        f"| **{_n(total.invalidos)}** | **{_n(total.eventos)}** | **{_n(total.vias['exata'])}** "
        f"| **{_n(total.vias['generica'])}** | **{_n(total.vias['sem_mapeamento'])}** "
        f"| **{_pct(mapeados, total.eventos)}** "
        f"| **{_pct(total.eventos - total.desconhecido, total.eventos)}** |\n"
    )

    por_via = Counter(a.via for a in assinaturas.values())
    add("## Por assinatura distinta\n")
    add("| Assinaturas | Exata | Genérica | Sem mapeamento |")
    add("| ---: | ---: | ---: | ---: |")
    add(
        f"| {len(assinaturas)} | {por_via['exata']} | {por_via['generica']} "
        f"| {por_via['sem_mapeamento']} |\n"
    )

    add("## Categorias atribuídas (todos os cenários)\n")
    add("| Categoria | Eventos | % |")
    add("| --- | ---: | ---: |")
    for categoria, n in total.categorias.most_common():
        add(f"| `{categoria}` | {_n(n)} | {_pct(n, total.eventos)} |")
    add("")

    add("## Acerto nos alertas causados por ataque\n")
    sem_rotulo = [c.nome for c in cenarios if c.rotulos_ok is not True]
    if sem_rotulo:
        add(f"Sem rótulos válidos em: {', '.join(sem_rotulo)}.\n")
    add(
        "Alertas com `event_label` diferente de `-` no CSV do AIT-ADS, comparados com a "
        "categoria esperada para o rótulo.\n"
    )
    add("| Rótulo | Esperada | Alertas | Acerto | Categorias obtidas |")
    add("| --- | --- | ---: | ---: | --- |")
    for rotulo, dados in sorted(acertos.items(), key=lambda x: -x[1]["eventos"]):
        esperado = ESPERADO_POR_ROTULO.get(rotulo)
        obtidas = ", ".join(f"`{c}` {_n(n)}" for c, n in dados["obtidas"].most_common())
        add(
            f"| `{rotulo}` | `{esperado.value if esperado else '?'}` | {_n(dados['eventos'])} "
            f"| {_pct(dados['acertos'], dados['eventos'])} | {obtidas} |"
        )
    add("")

    def tabela(titulo: str, filtro, texto: str) -> None:
        escolhidas = sorted(
            ((nome, a) for nome, a in assinaturas.items() if filtro(a)),
            key=lambda x: -sum(x[1].alertas.values()),
        )
        add(f"## {titulo} ({len(escolhidas)})\n")
        add(texto + "\n")
        if not escolhidas:
            add("Nenhuma.\n")
            return
        add(
            "| Assinatura | Grupos ou categoria de origem | Categoria | Decidida por "
            "| Alertas | Cenários | Causados por ataque |"
        )
        add("| --- | --- | --- | --- | ---: | --- | ---: |")
        for nome, a in escolhidas:
            cenarios_txt = ", ".join(sorted(a.alertas))
            add(
                f"| {nome.replace('|', '/')} | {a.grupos_ou_categoria} | `{a.categoria}` "
                f"| `{a.chave.split(':')[0] if a.via == 'sem_mapeamento' else a.chave}` "
                f"| {_n(sum(a.alertas.values()))} | {cenarios_txt} | {_n(a.ataque)} |"
            )
        add("")

    tabela(
        "Mapeadas só pelas regras genéricas",
        lambda a: a.via == "generica",
        "Não estão na taxonomia: a categoria veio de um grupo, da família ET ou da categoria "
        "do Suricata. Revisar antes de aprovar a taxonomia (D3 em docs/pendencias.md).",
    )
    tabela(
        "Sem mapeamento",
        lambda a: a.via == "sem_mapeamento",
        "Viraram `desconhecido` porque nada casou.",
    )
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cenarios", nargs="*", default=CENARIOS, choices=CENARIOS)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args(argv)

    faltando = [c for c in args.cenarios if not (AIT / "json" / f"{c}_wazuh.json").exists()]
    if faltando:
        print(f"faltam os JSON de: {', '.join(faltando)} (veja data/README.md)", file=sys.stderr)
        return 2

    adaptador = AdaptadorWazuh()
    assinaturas: dict[str, Assinatura] = {}
    acertos: dict = defaultdict(lambda: {"eventos": 0, "acertos": 0, "obtidas": Counter()})
    cenarios = []
    for nome in args.cenarios:
        c = medir(nome, adaptador, assinaturas, acertos)
        rotulos = {None: "sem CSV", True: "rótulos ok", False: "rótulos desalinhados"}[c.rotulos_ok]
        print(f"{nome}: {c.alertas} alertas em {c.segundos:.0f}s ({rotulos})", file=sys.stderr)
        cenarios.append(c)

    texto = relatorio(cenarios, assinaturas, acertos)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(texto + "\n", encoding="utf-8", newline="\n")
    print(texto)
    print(f"\nrelatório gravado em {args.saida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
