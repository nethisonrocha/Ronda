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
| `notificacao` | não | Política anti-fadiga (abaixo); sem o bloco, o tenant não recebe notificação |
| `correlacao.janela` | não (`30min`) | Intervalo máximo entre eventos da mesma chave para ficarem no mesmo incidente (1min a 7d) |
| `expediente` | não | Horário de trabalho do tenant (`fuso`, `dias`, `inicio`, `fim`); fora dele, o contexto marca `fora_do_horario` |

Categorias válidas: `comprometimento`, `ataque_web`, `negacao_servico`, `forca_bruta`,
`reconhecimento`, `exfiltracao`, `benigno`, `desconhecido`. A taxonomia foi aprovada pelo dono
em 06/10/2026; veja [exploracao-ait-ads.md](exploracao-ait-ads.md) e
[pendencias.md](pendencias.md).

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
negacao_servico é P2, forca_bruta e reconhecimento são P3, e benigno é P4. As categorias
novas: exfiltracao é P1 e desconhecido é P3. O rastro diz o que faltou.

## Correlação

```yaml
correlacao:
  janela: 30min
```

Eventos com a mesma **origem, categoria e ativo** viram um incidente enquanto chegarem com até
`janela` de intervalo entre si. Passada a janela sem evento novo, o incidente se encerra por
inatividade. O ativo da chave é o do inventário; sem ele, o nome informado pela fonte e depois o
IP. A prioridade do incidente é reavaliada quando ele nasce e quando a recorrência muda, e
**nunca diminui** enquanto ele estiver aberto.

A **recorrência** (`recorrencia_24h`) conta os eventos da mesma chave nas últimas 24 h, em
qualquer incidente, e **satura em 1000**. Por isso a política recusa modificador com limiar maior
que 1000.

## Notificação

```yaml
notificacao:
  canal: telegram
  destino_env: RONDA_TELEGRAM_CHAT_DEMO   # o chat id fica no .env, nunca no YAML
  fuso: America/Fortaleza
  modos: {P1: imediata, P2: agrupada, P3: resumo_diario, P4: nunca}
  agrupamento: 10min
  silencio_por_origem: 2h
  horario_silencio: {inicio: "22:00", fim: "07:00"}
  resumo_diario: "08:00"
```

| Regra | O que faz |
| --- | --- |
| `modos` | O que cada prioridade dispara; o que faltar vem do padrão acima. P1 não pode ser `nunca` |
| `agrupamento` | P2 da mesma origem (ferramenta) esperam a janela e saem numa mensagem só |
| `silencio_por_origem` | Depois de notificar uma chave (origem, categoria e ativo), um incidente novo dela no mesmo nível ou abaixo é registrado como suprimido; subir de nível sempre notifica. **Precisa ser maior que `correlacao.janela`** (padrão 2 h): um incidente novo da chave só nasce depois de uma janela sem evento, então, com o silêncio igual ou menor, a regra nunca age. A política recusa |
| `horario_silencio` | Nada sai, exceto o P1; o resto espera o fim do horário. Pode atravessar a meia-noite |
| `resumo_diario` | Os P3 pendentes saem numa mensagem por dia, neste horário, no fuso do tenant. O resumo conta por categoria (incidentes, ativos, eventos e os três ativos mais frequentes), em vez de listar incidente por incidente |

Toda notificação fica registrada, inclusive a suprimida, com o motivo. As mensagens trazem o que
houve, por que a prioridade (o rastro do motor) e a ação sugerida, e têm um botão **Reconhecer**
que registra o tempo até o reconhecimento.

## Modificadores

```yaml
modificadores:
  - se: recorrencia_24h >= 5
    subir: 1
    exceto: [forca_bruta, comprometimento]
  - se: recorrencia_24h >= 50
    subir: 1
    categorias: [forca_bruta]
  - se: ataque_previo_no_ativo
    subir: 1
    categorias: [comprometimento]
  - se: confirmado
    subir: 1
```

A condição é `campo` (verdadeiro/falso) ou `campo <op> valor`, com `>=`, `<=`, `>`, `<`,
`==` e `!=`. `categorias` limita o modificador às categorias listadas e `exceto` o tira delas
(um ou outro, não os dois); sem nenhum, ele vale para todas. No rastro, o escopo aparece junto da
condição: `recorrencia_24h >= 50 (só forca_bruta): urgência sobe para alta`. Campos
disponíveis:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `recorrencia_24h` | inteiro | Eventos iguais nas últimas 24 h |
| `confirmado` | verdadeiro/falso | Ataque confirmado pela fonte ou analista |
| `fora_do_horario` | verdadeiro/falso | Fora do `expediente` do tenant (falso se a política não tiver o bloco) |
| `ataque_previo_no_ativo` | verdadeiro/falso | O mesmo ativo teve, nas últimas 24 h, outro incidente P1 ou P2 de outra categoria: um passo anterior do ataque |

O pipeline só calcula `ataque_previo_no_ativo` se algum modificador o usa, porque ele custa uma
consulta ao banco por evento.

**Por que a demonstração usa escopo por categoria** (decisões do dono em 06/10/2026, com os
números da avaliação em [avaliacao-fase2.md](avaliacao-fase2.md)):

- **Força bruta com limiar próprio (A1).** Usuários errando a senha passam de 5 falhas por dia o
  tempo todo; com o limiar geral, 246 dos 257 P2 de força bruta eram ruído. Nenhum limiar separou
  o erro comum do ataque; 50 deixou 19 incidentes de ruído.
- **Comprometimento só vira P1 com contexto (A5).** O `sudo` de rotina e o da escalada de
  privilégio são o mesmo alerta. A urgência base é média (P2 em ativo crítico) e sobe fora do
  expediente ou depois de outro incidente grave no mesmo ativo.

Não há `eval`, e qualquer outro formato é recusado ao carregar a política.

## Antes de aplicar uma versão nova

Use `POST /politicas/<tenant>/simular` com a política candidata e uma lista de eventos. A
resposta diz quantos mudariam de prioridade, em quais transições (`P3→P1`) e com o rastro
de antes e depois.
