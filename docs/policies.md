# Como escrever uma política

Cada tenant tem um arquivo `<tenant>.yaml`, versionado, no diretório definido por
`RONDA_POLICIES_DIR`. O exemplo completo está em
[policies/examples/demo.yaml](../policies/examples/demo.yaml).

## Campos

| Campo | Obrigatório | Conteúdo |
| --- | --- | --- |
| `tenant` | sim | Igual ao nome do arquivo; minúsculas, dígitos e hífen |
| `versao` | sim | Inteiro ≥ 1; suba a cada mudança |
| `criticidade_padrao` | não (`media`) | Criticidade de ativo fora do inventário |
| `ativos` | não | `nome`, `rede` (CIDR, opcional) e `criticidade` (`alta`, `media`, `baixa`) |
| `impacto` | não | Por categoria, o impacto (`alto`, `medio`, `baixo`) para cada criticidade |
| `urgencia.base` | não | Por categoria, a urgência (`alta`, `media`, `baixa`) |
| `urgencia.modificadores` | não | Ajustes de urgência por contexto |
| `matriz` | sim | Impacto → urgência → prioridade; as 9 células são obrigatórias |
| `resposta` | não | Prazo por prioridade: `15min`, `1h`, `2d` |

Categorias válidas: `comprometimento`, `ataque_web`, `negacao_servico`, `forca_bruta`,
`reconhecimento`, `benigno`.

## Como o motor decide

1. **Ativo.** Procura primeiro pelo nome informado pela fonte, depois pelo IP de destino e
   depois pelo de origem. Se duas redes contêm o IP, vence a mais específica. Sem
   correspondência, vale `criticidade_padrao`.
2. **Impacto.** `impacto[categoria][criticidade]`.
3. **Urgência.** `urgencia.base[categoria]`, e depois cada modificador cuja condição é
   verdadeira, na ordem do arquivo. A urgência para em `alta` e em `baixa`. Um ajuste que
   já está na ponta aparece no rastro como "sem efeito".
4. **Prioridade.** `matriz[impacto][urgencia]`, com o prazo de `resposta`. Uma prioridade
   sem prazo, como P4 no exemplo, aparece como "sem prazo de resposta".

**Categoria sem regra.** Se a categoria não tiver linha em `impacto` ou em `urgencia.base`,
vale a prioridade base da taxonomia, herdada do TCC: comprometimento e ataque_web são P1,
negacao_servico é P2, forca_bruta e reconhecimento são P3, e benigno é P4. O rastro diz o
que faltou.

## Modificadores

```yaml
modificadores:
  - se: recorrencia_24h >= 5
    subir: 1
  - se: confirmado
    subir: 1
  - se: fora_do_horario
    descer: 1
```

A condição é `campo` (verdadeiro/falso) ou `campo <op> valor`, com `>=`, `<=`, `>`, `<`,
`==` e `!=`. Campos disponíveis:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `recorrencia_24h` | inteiro | Eventos iguais nas últimas 24 h |
| `confirmado` | verdadeiro/falso | Ataque confirmado pela fonte ou analista |
| `fora_do_horario` | verdadeiro/falso | Fora do expediente do tenant |

Não há `eval`, e qualquer outro formato é recusado ao carregar a política.

## Antes de aplicar uma versão nova

Use `POST /politicas/<tenant>/simular` com a política candidata e uma lista de eventos. A
resposta diz quantos mudariam de prioridade, em quais transições (`P3→P1`) e com o rastro
de antes e depois.
