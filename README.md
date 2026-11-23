# Ronda

Camada aberta de **governança ITIL para alertas de segurança**. Recebe alertas de Wazuh,
Suricata ou do detector do TCC, normaliza em um esquema único, correlaciona em incidentes,
prioriza em **P1 a P4** por uma matriz Impacto × Urgência configurável por organização, registra o
**rastro auditável de decisão** e notifica em português apenas quando importa.

O produto é a camada de governança, não o detector: qualquer ferramenta vira fonte por meio
de um adaptador ([ADR 0002](docs/adr/0002-governanca-independente-do-detector.md)).

> Origem acadêmica: evolução arquitetural do TCC *"Aplicação de Inteligência Artificial na
> Governança de Infraestrutura"* (Engenharia de Telecomunicações, UFC, 2026). Especificação em
> [docs/especificacao.md](docs/especificacao.md) e plano de entregas em
> [docs/plano-desenvolvimento.md](docs/plano-desenvolvimento.md).

## Resultados medidos (AIT-ADS)

Avaliado sobre **~2,6 milhões de alertas** nos 8 cenários do conjunto AIT-ADS (39,7 dias de
operação simulada em [docs/avaliacao-fase2.md](docs/avaliacao-fase2.md)):

| Métrica | Política inicial (v3) | Política calibrada (v4) |
| --- | ---: | ---: |
| Incidentes correlacionados | 14.797 | **14.701** |
| Incidentes P1 / P2 | 153 / 257 | **22 / 12** |
| Mensagens enviadas ao Telegram | 450 | **79** |
| Mensagens urgentes (P1/P2) | 402 (10/dia) | **31 (0,8/dia)** |
| Supressões anti-fadiga (silêncio por origem) | 0 | **862** |
| Escalada de privilégio e ataque web detectados | 8 de 8 cenários | **8 de 8 cenários** |

**Redução de ~13× nas notificações urgentes P1/P2** mantendo a detecção dos ataques reais onde as
fontes os enxergam.

## Situação das fases

| Fase | Entregas | Estado |
| --- | --- | --- |
| 1. Núcleo | Esquema de evento, motor determinístico com rastro, política em YAML, testes, API | **concluída** |
| 2. Alertas | Adaptador Wazuh, ingestão Redis Streams, PostgreSQL + RLS, correlação, Telegram anti-fadiga | **concluída** *(falta rodar na VPS real)* |
| 3. Produto visível | Adaptador Suricata (`eve.json`), API `/v1/incidentes` e `/v1/metricas`, Dashboard Next.js, Docker Compose completo, amostras `samples/` | **concluída** |
| 4. IA | Tradutor com LLM local (Ollama/`llama.cpp`) e detector XGBoost do TCC como fonte | **planejada** |
| 5. Maturidade | Reteste no CSE-CIC-IDS2018, monitoramento de drift, NOC híbrido, observabilidade, Terraform AWS | **planejada** |

## Do TCC ao Ronda

No TCC original, um classificador XGBoost (Recall P1 95,06 %, F1 Macro 97,44 % no CIC-IDS2017)
predizia diretamente `P1–P4` usando um mapeamento estático por família de ataque. O Ronda
generalizou a abordagem para operação multi-tenant:

1. **Detecção desacoplada:** Wazuh, Suricata (`eve.json`) ou o modelo do TCC convertem alertas em
   `Evento` com 8 categorias internas.
2. **Impacto dinâmico:** `categoria × criticidade do ativo` (resolvido no inventário por nome, IP ou
   rede CIDR mais específica).
3. **Urgência contextual:** base da categoria ajustada por `recorrencia_24h`, `fora_do_horario`,
   `ataque_previo_no_ativo` e `confirmado`.
4. **Rastro e anti-fadiga:** decisão gravada em tabela *append-only* apenas quando a prioridade sobe
   ([ADR 0003](docs/adr/0003-decisao-gravada-apenas-na-subida-de-prioridade.md)), com silêncio
   por origem, horário de silêncio (que só P1 fura), agrupamento P2 e resumo diário P3.

Veja [docs/policies.md](docs/policies.md) para escrever uma política e
[policies/examples/demo.yaml](policies/examples/demo.yaml) para um exemplo completo.

## Rodando com Docker (stack completa)

Copie `.env.example` para `.env`, ajuste as senhas e suba PostgreSQL, Redis, migrations Alembic,
API (`:8000`), Worker e Dashboard (`:3000`):

```sh
cp .env.example .env
docker compose -f deploy/docker/docker-compose.yml --env-file .env up -d --build
```

Acesse:
- **Dashboard Web (inclui Modo Demo sem backend):** <http://127.0.0.1:3000>
- **Documentação interativa da API:** <http://127.0.0.1:8000/docs>

## Rodando localmente em desenvolvimento

Requer [uv](https://docs.astral.sh/uv/), Python 3.12+ e Node.js 22+ (para o dashboard).

```sh
uv sync
uv run pytest -m "not integracao" -q          # testes unitários
uv run uvicorn ronda.api.main:app --reload    # API em http://127.0.0.1:8000/docs
```

Para o dashboard em desenvolvimento:

```sh
cd dashboard && npm install && npm run dev    # http://127.0.0.1:3000
```

Para testes completos (incluindo os 88 testes de integração com PostgreSQL/RLS) ou replay com
PostgreSQL + Redis locais (`make up`), consulte [CLAUDE.md](CLAUDE.md#ambiente-local-postgresql-e-redis).

## Estrutura

| Pasta | Conteúdo |
| --- | --- |
| `src/ronda/domain/` | Núcleo puro, sem I/O: evento, incidente, notificação, taxonomia, escalas ITIL |
| `src/ronda/governance/` | Política YAML, motor determinístico, rastro auditável e simulação |
| `src/ronda/adapters/` | Adaptadores plugáveis (`wazuh/`, `suricata/` nativo `eve.json`, placeholders `detector_tcc/` e `webhook/`) |
| `src/ronda/correlation/` | Agrupamento temporal por janela e reavaliação monotônica |
| `src/ronda/storage/` | SQLAlchemy 2, Alembic (4 migrations), RLS multi-tenant e repositórios de métricas |
| `src/ronda/notifier/` | Roteamento anti-fadiga, resumo diário e canal Telegram |
| `src/ronda/api/` | FastAPI (`/v1/ingestao`, `/v1/incidentes`, `/v1/metricas`, `/v1/politicas`, `/v1/eventos`) |
| `dashboard/` | Interface web em Next.js (fila P1–P4, rastro ITIL, simulador de política e Modo Demo) |
| `deploy/docker/` | Dockerfiles e Compose de stack completa |
| `samples/` | Recortes reais redistribuíveis do AIT-ADS (CC BY 4.0) para demo e replay |
| `data/` | Datasets **fora do git**; só manifesto e README versionados ([data/README.md](data/README.md)) |
| `docs/adr/` | Registros de decisão arquitetural (`0001` a `0003`) |

## Licença

[Apache 2.0](LICENSE). Amostras do AIT-ADS em `samples/` seguem a licença CC BY 4.0 dos autores originais ([samples/README.md](samples/README.md)).
