# Arquitetura

A arquitetura é independente do detector: qualquer ferramenta vira fonte por meio de um
adaptador, e o valor do projeto está da ingestão para baixo ([ADR 0002](adr/0002-governanca-independente-do-detector.md)).
Visão completa em [especificacao.md](especificacao.md).

```
fontes (Wazuh, Suricata eve.json, detector do TCC*, webhook*)
  → adapters/        alerta da ferramenta → Evento (esquema único)
  → fila             Redis Streams, separa ingestão de processamento
  → correlation/     eventos → Incidente + Contexto (recorrência, expediente, ataque prévio)
  → governance/      política do tenant → P1–P4 + rastro determinístico
  → translator/      mensagem em português (templates Jinja2; LLM local na fase 4)
  → notifier/        política anti-fadiga → Telegram
  → storage/ + api/  PostgreSQL 16 com RLS + FastAPI (/v1/*)
  → dashboard/       Next.js (fila P1–P4, rastro auditável, simulador de política)
```

*\* `detector_tcc/` e `webhook/` estão previstos nas Fases 4 e B.*

## Camadas e regras de dependência

- `domain/` não importa nada do projeto além de si mesmo e não faz I/O.
- `governance/` depende só de `domain/`. O motor é determinístico: a mesma entrada produz a
  mesma decisão, o que torna a simulação de política possível.
- Adaptadores, storage, workers, notificador e API ficam na borda e dependem do núcleo, nunca o
  contrário.

## Estado atual (Fases 1, 2 e 3 no código)

- **Domínio e governança:** esquema de evento, taxonomia de 8 categorias, escalas ITIL, política em
  YAML com validação, motor com rastro e simulação ("antes vs. depois").
- **Ingestão e persistência:** adaptadores Wazuh e Suricata (`eve.json`), `POST /v1/ingestao/{origem}`
  autenticado por token SHA-256, Redis Streams, PostgreSQL 16 com RLS multi-tenant e tabelas
  *append-only* (`decisoes` e `auditoria`).
- **Correlação e notificação:** agrupamento por janela, prioridade monotônica, roteador
  anti-fadiga, resumo diário por categoria e Telegram com reconhecimento.
- **API operacional e Dashboard:** endpoints `/v1/incidentes`, `/v1/incidentes/{id}`,
  `/v1/incidentes/{id}/reconhecer` e `/v1/metricas/resumo` consumidos pelo dashboard Next.js em
  `dashboard/`, além de empacotamento Docker em `deploy/docker/`.

Decisões arquiteturais registradas:
- [ADR 0001 — Regras do motor para lacunas da política](adr/0001-regras-do-motor-para-lacunas-da-politica.md)
- [ADR 0002 — Governança independente do detector](adr/0002-governanca-independente-do-detector.md)
- [ADR 0003 — Gravação de decisão apenas na subida monotônica de prioridade](adr/0003-decisao-gravada-apenas-na-subida-de-prioridade.md)
