# Ronda

Camada aberta de **governança ITIL para alertas de segurança**. Recebe alertas de Wazuh,
Suricata ou do detector do TCC, prioriza cada um em **P1 a P4** por uma matriz
Impacto × Urgência configurável por organização, registra o **rastro de decisão** e notifica
em português, só quando importa.

O produto é a camada de governança, não o detector: qualquer ferramenta vira fonte por meio
de um adaptador.

> Proposta original: TCC "Aplicação de Inteligência Artificial na Governança de
> Infraestrutura" (Engenharia de Telecomunicações, UFC, 2026). Especificação completa em
> [docs/especificacao.md](docs/especificacao.md).

## Situação

| Fase | Entregas | Estado |
| --- | --- | --- |
| 1. Núcleo | Esquema de evento, motor de governança, política em YAML, testes, API mínima | **em andamento** |
| 2. Alertas | Adaptador Wazuh, correlação, Telegram, resumo diário | — |
| 3. Produto visível | Dashboard, simulação na interface, Suricata, demo em replay | — |
| 4. IA | Tradutor com LLM local, detector do TCC como fonte | — |
| 5. Maturidade | Reteste no CSE-CIC-IDS2018, drift, multi-tenant completo | — |

## Como a prioridade é decidida

```
negacao_servico → ativo servidor-pagamentos (criticidade alta) → impacto alto
  → urgência alta → P1, resposta em 15 min
```

1. O inventário da política resolve o ativo (pelo nome, pelo IP de destino ou pelo de origem).
2. Categoria × criticidade do ativo dá o **impacto**.
3. A categoria dá a **urgência**, ajustada por modificadores (recorrência, ataque confirmado,
   fora do horário).
4. A matriz Impacto × Urgência dá a **prioridade** e o prazo de resposta.

Veja [docs/policies.md](docs/policies.md) para escrever uma política e
[policies/examples/demo.yaml](policies/examples/demo.yaml) para um exemplo completo.

## Rodando localmente

Requer [uv](https://docs.astral.sh/uv/) e Python 3.12 ou mais recente.

```sh
uv sync
uv run pytest
uv run uvicorn ronda.api.main:app --reload   # http://127.0.0.1:8000/docs
```

Com `make`: `make test`, `make lint`, `make api`.

```sh
curl -s localhost:8000/eventos/avaliar -H 'content-type: application/json' -d '{
  "evento": {"tenant_id": "demo", "origem": "wazuh", "categoria": "negacao_servico",
             "ip_destino": "10.0.1.5", "ocorrido_em": "2026-09-25T14:03:11Z"}
}'
```

## Estrutura

| Pasta | Conteúdo |
| --- | --- |
| `src/ronda/domain` | Núcleo puro, sem I/O: evento, incidente, taxonomia, escalas ITIL |
| `src/ronda/governance` | Política, motor, rastro e simulação |
| `src/ronda/adapters` | Uma fonte por pasta, todas com a mesma interface |
| `src/ronda/api` | FastAPI |
| `detector/` | Módulo do TCC, com dependências de ML separadas |
| `data/` | Datasets, **fora do git**; só manifesto e README versionados ([data/README.md](data/README.md)) |
| `scripts/` | `download_data.py`: baixa, confere checksum e descompacta (`make data`) |
| `samples/` | Poucos alertas redistribuíveis, para a demo |
| `policies/examples/` | Políticas de exemplo por tenant |
| `docs/adr/` | Registros de decisão |

## Licença

[Apache 2.0](LICENSE).
