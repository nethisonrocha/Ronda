# Cobertura do mapeamento do Wazuh no AIT-ADS

Gerado por `scripts/cobertura_mapeamento.py` com o `mapping.yaml` atual (taxonomia aprovada em 06/10/2026). Cada alerta passou pelo `AdaptadorWazuh`.

- **exata**: regra ou assinatura listada na taxonomia;
- **genérica**: grupo do Wazuh, família ET ou categoria do Suricata;
- **sem mapeamento**: nada casou; vira `desconhecido`;
- **cobertura** = (exata + genérica) / eventos; **categoria útil** = eventos que não terminaram em `desconhecido` (inclui os mapeados para `desconhecido` de propósito, como as anomalias de protocolo).

## Por cenário

| Cenário | Alertas | Descartados (fast.log) | Inválidos | Eventos | Exata | Genérica | Sem mapeamento | Cobertura | Categoria útil |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fox | 462.523 | 11.084 | 0 | 451.439 | 451.439 | 0 | 0 | 100.00% | 97.62% |
| harrison | 583.754 | 67.411 | 0 | 516.343 | 516.343 | 0 | 0 | 100.00% | 87.06% |
| russellmitchell | 41.488 | 9.186 | 0 | 32.302 | 32.302 | 0 | 0 | 100.00% | 72.56% |
| santos | 126.513 | 44.112 | 0 | 82.401 | 82.401 | 0 | 0 | 100.00% | 46.86% |
| shaw | 68.539 | 16.708 | 0 | 51.831 | 51.831 | 0 | 0 | 100.00% | 68.78% |
| wardbeck | 88.204 | 24.510 | 0 | 63.694 | 63.694 | 0 | 0 | 100.00% | 62.17% |
| wheeler | 603.939 | 68.674 | 0 | 535.265 | 535.265 | 0 | 0 | 100.00% | 87.25% |
| wilson | 625.303 | 65.038 | 0 | 560.265 | 560.265 | 0 | 0 | 100.00% | 88.48% |
| **Total** | **2.600.263** | **306.723** | **0** | **2.293.540** | **2.293.540** | **0** | **0** | **100.00%** | **86.78%** |

## Por assinatura distinta

| Assinaturas | Exata | Genérica | Sem mapeamento |
| ---: | ---: | ---: | ---: |
| 53 | 53 | 0 | 0 |

## Categorias atribuídas (todos os cenários)

| Categoria | Eventos | % |
| --- | ---: | ---: |
| `reconhecimento` | 1.696.048 | 73.94% |
| `desconhecido` | 303.186 | 13.21% |
| `benigno` | 288.959 | 12.59% |
| `forca_bruta` | 2.698 | 0.11% |
| `ataque_web` | 2.606 | 0.11% |
| `comprometimento` | 43 | 0.00% |

## Acerto nos alertas causados por ataque

Alertas com `event_label` diferente de `-` no CSV do AIT-ADS, comparados com a categoria esperada para o rótulo.

| Rótulo | Esperada | Alertas | Acerto | Categorias obtidas |
| --- | --- | ---: | ---: | --- |
| `dirb` | `reconhecimento` | 1.670.616 | 99.84% | `reconhecimento` 1.668.022, `ataque_web` 2.575, `desconhecido` 19 |
| `dnsteal` | `exfiltracao` | 72.890 | 0.00% | `desconhecido` 72.890 |
| `wpscan` | `reconhecimento` | 27.288 | 99.66% | `reconhecimento` 27.197, `ataque_web` 31, `desconhecido` 30, `forca_bruta` 30 |
| `service_scan` | `reconhecimento` | 258 | 91.47% | `reconhecimento` 236, `desconhecido` 22 |
| `escalated_sudo_command` | `comprometimento` | 56 | 42.85% | `benigno` 32, `comprometimento` 24 |
| `attacker_change_user` | `comprometimento` | 22 | 36.36% | `benigno` 14, `comprometimento` 8 |
| `online_cracking` | `forca_bruta` | 6 | 0.00% | `desconhecido` 6 |

## Mapeadas só pelas regras genéricas (0)

Não estão na taxonomia: a categoria veio de um grupo, da família ET ou da categoria do Suricata. Revisar antes de aprovar a taxonomia (D3 em docs/pendencias.md).

Nenhuma.

## Sem mapeamento (0)

Viraram `desconhecido` porque nada casou.

Nenhuma.

