"""Taxonomia interna de categorias, comum a todas as fontes.

Cada adaptador traduz os rótulos da sua ferramenta (grupos de regra do Wazuh,
classes do Suricata, rótulos do modelo do TCC) para uma destas categorias.
"""

from enum import StrEnum

from ronda.domain.priority import Prioridade


class Categoria(StrEnum):
    comprometimento = "comprometimento"
    ataque_web = "ataque_web"
    negacao_servico = "negacao_servico"
    forca_bruta = "forca_bruta"
    reconhecimento = "reconhecimento"
    benigno = "benigno"


# Prioridade herdada do TCC. Vale quando a política do tenant não tem regra para
# a categoria; com regra, a política sempre decide.
PRIORIDADE_BASE: dict[Categoria, Prioridade] = {
    Categoria.comprometimento: Prioridade.P1,
    Categoria.ataque_web: Prioridade.P1,
    Categoria.negacao_servico: Prioridade.P2,
    Categoria.forca_bruta: Prioridade.P3,
    Categoria.reconhecimento: Prioridade.P3,
    Categoria.benigno: Prioridade.P4,
}
