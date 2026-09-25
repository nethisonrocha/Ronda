# Armazenamento

PostgreSQL 16 com SQLAlchemy 2 (síncrono, driver psycopg 3) e Alembic. O código fica em
`src/ronda/storage/`:

| Arquivo | Conteúdo |
| --- | --- |
| `models.py` | Modelos ORM de todas as tabelas |
| `database.py` | `BancoDeDados` e a sessão por tenant |
| `repositories.py` | Tradução entre o domínio e as tabelas |
| `migrations/` | Alembic; a revisão `0001` cria o esquema, a RLS e os triggers |

## Tabelas

| Tabela | Guarda | Observação |
| --- | --- | --- |
| `tenants` | Organizações | A RLS mostra só a própria linha |
| `eventos` | Alertas normalizados (`Evento`) com o alerta original em `bruto` | Único por `(tenant_id, origem, id_origem)`: ingestão idempotente |
| `incidentes` | Agrupamento de eventos (`Incidente`) com estado, prioridade atual e contagem | No máximo **um incidente ativo** por chave de correlação (origem, categoria, ativo) |
| `decisoes` | Cada avaliação do motor, com o **rastro em JSONB** e o resumo legível | **Somente inserção**; aponta para um evento, para um incidente ou para os dois |
| `notificacoes` | Envios por canal, inclusive os suprimidos pela política anti-fadiga, com o motivo | Fila de envio com `SKIP LOCKED`, tentativas e reconhecimento |
| `auditoria` | Quem fez o quê (ator, ação, entidade, dados) | **Somente inserção** |

Um incidente guarda o **total** de eventos, e não a lista. Cada evento aponta para o seu
incidente (`eventos.incidente_id`). No AIT-ADS, um único incidente de varredura pode ter
centenas de milhares de eventos.

## Isolamento entre tenants

São três camadas independentes, e cada uma segura sozinha:

1. **Repositório.** Toda consulta filtra por `tenant_id`, e gravar um objeto de outro tenant
   levanta `OutroTenant` antes de chegar ao banco.
2. **Row-Level Security** com `FORCE` em todas as tabelas. A política `isolamento_tenant` compara
   `tenant_id` com `current_setting('app.tenant_id', true)`, e isso vale tanto para leitura quanto
   para escrita. Sem tenant definido, nada é visível nem gravável.
3. **Chaves compostas.** Toda chave primária é `(tenant_id, id)`, e toda chave estrangeira entre
   tabelas de tenant inclui o `tenant_id`. Uma decisão do tenant A não consegue apontar para um
   evento do tenant B, nem pelo dono, que ignora a RLS.

**Sessão.** `BancoDeDados.sessao(tenant_id)` abre uma transação e executa
`set_config('app.tenant_id', tenant_id, true)`. O `true` limita o valor à transação, então a
conexão volta ao pool sem tenant; há um teste que prova isso com a mesma conexão física.

**Papéis.**

| Papel | Uso | Situação |
| --- | --- | --- |
| `ronda` | Dono das tabelas, roda as migrations | Superusuário no compose de dev, porque a imagem oficial o cria assim; nunca usado pela aplicação |
| `ronda_app` | Papel da aplicação | Não é dono das tabelas nem tem `BYPASSRLS` |

A migration não cria papéis nem `GRANT`s, porque isso depende do ambiente. No compose, o
`deploy/compose/initdb/` cria o `ronda_app` com privilégios padrão; nos testes, a fixture faz o
mesmo.

## Somente inserção

O trigger `ronda_somente_insercao` recusa `UPDATE` e `DELETE` em `decisoes` e `auditoria`, e vale
também para superusuário. Uma reavaliação grava uma decisão nova. O histórico de um incidente
é a sequência das suas decisões (`RepositorioDecisoes.do_incidente`).

## Migrations

```sh
uv run alembic upgrade head          # usa RONDA_DATABASE_MIGRATION_URL do .env
uv run alembic current
uv run alembic upgrade head --sql    # só mostra o SQL
uv run alembic -x url=postgresql+psycopg://... upgrade head
```

Uma migration nova é **escrita à mão**, com número sequencial (`--rev-id 0002`), e não importa
código do projeto. Os modelos e as migrations precisam descrever o mesmo esquema: o teste
`test_modelos_e_migration_descrevem_o_mesmo_esquema` compara os dois com o autogenerate do
Alembic e falha em qualquer diferença. Tabela nova de tenant precisa de três coisas na mesma
migration: RLS com `FORCE`, a política `isolamento_tenant` e as chaves compostas.

## Testes

`tests/integration/storage/` roda contra um PostgreSQL 16 real, com testcontainers:

- um container por sessão de testes, e as tabelas zeradas antes de cada teste;
- as migrations rodam como dono e os repositórios como `ronda_app`;
- sem Docker, os testes são pulados.

```sh
uv run pytest -m integracao          # só os de integração (exigem Docker)
uv run pytest -m "not integracao"    # só os rápidos
```
