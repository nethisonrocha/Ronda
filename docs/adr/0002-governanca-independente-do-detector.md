# ADR 0002 — Governança independente do detector

- **Data:** 2026-11-23
- **Estado:** aceita

## Contexto

No TCC que deu origem ao projeto, um classificador supervisionado (XGBoost) recebia fluxos de rede e predizia diretamente a prioridade ITIL (P1–P4) a partir de um mapeamento estático por família de ataque. Em operação real, porém, a mesma ameaça tem impacto e urgência diferentes conforme a criticidade do ativo atingido, o horário e a recorrência — e o detector pode ser um SIEM (Wazuh), um NIDS (Suricata) ou o próprio modelo de ML.

## Decisão

1. **O produto é a camada de governança, não o detector.** O núcleo (`domain/` e `governance/`) não importa adaptadores nem modelos de ML e não executa I/O.
2. **Todo detector é uma fonte plugável** por meio de um adaptador que traduz o alerta bruto da ferramenta para o esquema único `Evento` e a taxonomia interna de 8 categorias (`comprometimento`, `ataque_web`, `negacao_servico`, `forca_bruta`, `reconhecimento`, `exfiltracao`, `benigno`, `desconhecido`).
3. **A prioridade P1–P4 é calculada deterministicamente** pelo `Motor` a partir da política YAML do *tenant* (inventário de ativos, matriz Impacto × Urgência e modificadores contextuais), usando a prioridade herdada do TCC (`PRIORIDADE_BASE`) apenas como reserva quando a política omite uma categoria.

## Consequências

- Trocar ou adicionar fontes de detecção (Wazuh, Suricata, detector do TCC, webhooks NOC) exige apenas um novo adaptador, sem alterar correlação, governança, persistência ou notificação.
- O motor pode simular mudanças de política sobre eventos históricos de forma determinística e auditável.
