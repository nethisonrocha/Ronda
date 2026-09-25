# Arquitetura

A arquitetura é independente do detector: qualquer ferramenta vira fonte por meio de um
adaptador, e o valor do projeto está da ingestão para baixo. Visão completa em
[especificacao.md](especificacao.md).

```
fontes (Wazuh, Suricata, detector do TCC, webhook)
  → adapters/        alerta da ferramenta → Evento (esquema único)
  → fila             Redis Streams, separa ingestão de processamento
  → correlation/     eventos → Incidente + Contexto (recorrência, confirmação)
  → governance/      política do tenant → P1–P4 + rastro
  → translator/      mensagem em português (template; LLM local depois)
  → notifier/        política anti-fadiga → Telegram
  → storage/ + api/  PostgreSQL com RLS, FastAPI, dashboard
```

## Camadas e regras de dependência

- `domain/` não importa nada do projeto além de si mesmo e não faz I/O.
- `governance/` depende só de `domain/`. O motor é determinístico: a mesma entrada produz a
  mesma decisão, o que torna a simulação de política possível.
- Adaptadores, storage, workers e API ficam na borda e dependem do núcleo, nunca o
  contrário.

## Estado atual (fase 1)

Prontos: esquema de evento, taxonomia, escalas ITIL, política em YAML com validação, motor
com rastro, simulação e API sem persistência (`POST /eventos/avaliar`,
`GET /politicas/{tenant}`, `POST /politicas/{tenant}/simular`).

Decisões de comportamento do motor: [ADR 0001](adr/0001-regras-do-motor-para-lacunas-da-politica.md).
