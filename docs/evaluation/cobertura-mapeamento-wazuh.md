# Cobertura do mapeamento do Wazuh no AIT-ADS

Gerado por `scripts/cobertura_mapeamento.py` com o `mapping.yaml` atual (taxonomia provisória). Cada alerta passou pelo `AdaptadorWazuh`.

- **exata**: regra ou assinatura listada na taxonomia;
- **genérica**: grupo do Wazuh, família ET ou categoria do Suricata;
- **sem mapeamento**: nada casou; vira `desconhecido`;
- **cobertura** = (exata + genérica) / eventos; **categoria útil** = eventos que não terminaram em `desconhecido` (inclui os mapeados para `desconhecido` de propósito, como as anomalias de protocolo).

## Por cenário

| Cenário | Alertas | Descartados (fast.log) | Inválidos | Eventos | Exata | Genérica | Sem mapeamento | Cobertura | Categoria útil |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fox | 462.523 | 11.084 | 0 | 451.439 | 451.439 | 0 | 0 | 100.00% | 97.62% |
| harrison | 583.754 | 67.411 | 0 | 516.343 | 516.342 | 0 | 1 | 99.99% | 96.19% |
| russellmitchell | 41.488 | 9.186 | 0 | 32.302 | 32.302 | 0 | 0 | 100.00% | 72.55% |
| santos | 126.513 | 44.112 | 0 | 82.401 | 82.283 | 117 | 1 | 99.99% | 78.06% |
| shaw | 68.539 | 16.708 | 0 | 51.831 | 51.829 | 2 | 0 | 100.00% | 68.78% |
| wardbeck | 88.204 | 24.510 | 0 | 63.694 | 63.677 | 16 | 1 | 99.99% | 62.17% |
| wheeler | 603.939 | 68.674 | 0 | 535.265 | 535.239 | 26 | 0 | 100.00% | 90.77% |
| wilson | 625.303 | 65.038 | 0 | 560.265 | 560.240 | 13 | 12 | 99.99% | 88.47% |
| **Total** | **2.600.263** | **306.723** | **0** | **2.293.540** | **2.293.351** | **174** | **15** | **99.99%** | **90.77%** |

## Por assinatura distinta

| Assinaturas | Exata | Genérica | Sem mapeamento |
| ---: | ---: | ---: | ---: |
| 53 | 39 | 11 | 3 |

## Categorias atribuídas (todos os cenários)

| Categoria | Eventos | % |
| --- | ---: | ---: |
| `reconhecimento` | 1.695.982 | 73.94% |
| `benigno` | 288.959 | 12.59% |
| `desconhecido` | 211.491 | 9.22% |
| `exfiltracao` | 91.761 | 4.00% |
| `forca_bruta` | 2.695 | 0.11% |
| `ataque_web` | 2.609 | 0.11% |
| `comprometimento` | 43 | 0.00% |

## Acerto nos alertas causados por ataque

Alertas com `event_label` diferente de `-` no CSV do AIT-ADS, comparados com a categoria esperada para o rótulo.

| Rótulo | Esperada | Alertas | Acerto | Categorias obtidas |
| --- | --- | ---: | ---: | --- |
| `dirb` | `reconhecimento` | 1.670.616 | 99.84% | `reconhecimento` 1.668.022, `ataque_web` 2.575, `desconhecido` 19 |
| `dnsteal` | `exfiltracao` | 72.890 | 100.00% | `exfiltracao` 72.890 |
| `wpscan` | `reconhecimento` | 27.288 | 99.66% | `reconhecimento` 27.197, `ataque_web` 34, `desconhecido` 30, `forca_bruta` 27 |
| `service_scan` | `reconhecimento` | 258 | 69.76% | `reconhecimento` 180, `desconhecido` 78 |
| `escalated_sudo_command` | `comprometimento` | 56 | 42.85% | `benigno` 32, `comprometimento` 24 |
| `attacker_change_user` | `comprometimento` | 22 | 36.36% | `benigno` 14, `comprometimento` 8 |
| `online_cracking` | `forca_bruta` | 6 | 0.00% | `desconhecido` 6 |

## Mapeadas só pelas regras genéricas (11)

Não estão na taxonomia: a categoria veio de um grupo, da família ET ou da categoria do Suricata. Revisar antes de aprovar a taxonomia (D3 em docs/pendencias.md).

| Assinatura | Grupos ou categoria de origem | Categoria | Decidida por | Alertas | Cenários | Causados por ataque |
| --- | --- | --- | --- | ---: | --- | ---: |
| suricata · ET DNS Query for .cc TLD | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 48 | santos, wheeler, wilson | 0 |
| suricata · ET HUNTING Possible COVID-19 Domain in SSL Certificate M2 | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 47 | santos | 0 |
| suricata · ET HUNTING Suspicious Domain Request for Possible COVID-19 Domain M1 | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 27 | santos | 0 |
| suricata · ET HUNTING Suspicious TLS SNI Request for Possible COVID-19 Domain M1 | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 21 | santos | 0 |
| suricata · ET INFO TLS Handshake Failure | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 12 | wardbeck, wheeler, wilson | 0 |
| suricata · SURICATA TLS certificate invalid der | Generic Protocol Command Decode | `desconhecido` | `suricata.categorias:Generic Protocol Command Decode` | 4 | santos | 0 |
| suricata · ET DNS DNS Lookup for localhost.DOMAIN.TLD | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 4 | wardbeck | 0 |
| suricata · ET DNS Query to a *.pw domain - Likely Hostile | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 4 | wilson | 0 |
| wazuh · 31510 CMS (WordPress or Joomla) brute force attempt. | web, appsec, attack | `ataque_web` | `wazuh.grupos:attack` | 3 | wardbeck, wheeler, wilson | 3 |
| suricata · ET SCAN Behavioral Unusual Port 445 traffic Potential Scan or Infection | Misc activity | `reconhecimento` | `suricata.familias_et:SCAN` | 2 | shaw | 0 |
| suricata · ET DNS Query for .su TLD (Soviet Union) Often Malware Related | Potentially Bad Traffic | `desconhecido` | `suricata.categorias:Potentially Bad Traffic` | 2 | wardbeck | 0 |

## Sem mapeamento (3)

Viraram `desconhecido` porque nada casou.

| Assinatura | Grupos ou categoria de origem | Categoria | Decidida por | Alertas | Cenários | Causados por ataque |
| --- | --- | --- | --- | ---: | --- | ---: |
| suricata · ET INFO Session Traversal Utilities for NAT (STUN Binding Request) | Attempted User Privilege Gain | `desconhecido` | `suricata.assinaturas` | 10 | wardbeck, wilson | 0 |
| suricata · SURICATA DNS Unsolicited response | None | `desconhecido` | `suricata.assinaturas` | 3 | harrison, santos, wilson | 0 |
| suricata · ET INFO Session Traversal Utilities for NAT (STUN Binding Response) | Attempted User Privilege Gain | `desconhecido` | `suricata.assinaturas` | 2 | wilson | 0 |

