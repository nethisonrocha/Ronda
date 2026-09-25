# Avaliação da fase 2 nos 8 cenários do AIT-ADS

Rodada em 25/09/2026 pelo notebook [`notebooks/02_avaliar_fase2.ipynb`](../notebooks/02_avaliar_fase2.ipynb)
sobre os 2,6 milhões de alertas dos 8 cenários (39,7 dias de laboratório somados).

**Resumo:**

- **A redução funciona.** 2.293.540 eventos viraram 14.797 incidentes (155 por incidente) e
  **450 mensagens** (5.097 eventos por mensagem): 402 P1/P2 e 48 resumos diários.
- **O ataque é visto onde as fontes o veem.** As duas etapas que o Wazuh e o Suricata detectam de
  fato geraram P1/P2 nos 8 cenários: o ataque à aplicação web (`wpscan` ou `dirb`) e a escalada de
  privilégio.
- **O critério da tarefa não foi atingido.** Pela leitura estrita, só 18 dos 68 pares
  fase × cenário *geraram* um P1/P2. Em 30 pares, nenhuma fonte produziu um alerta causado pelo
  ataque, e nenhuma política conserta isso.
- **A precisão é o problema.** 378 dos 410 incidentes P1/P2 (92%) subiram por um evento fora de
  qualquer ataque. Três causas explicam todos eles:
  - força bruta de usuários comuns;
  - DNS para `.biz`;
  - `sudo` de rotina.

  São cerca de 10 mensagens urgentes por dia de laboratório, e quase todas são ruído.

## 1. Como foi medido

- **O pipeline é o do worker, em memória.** `ronda.avaliacao.Simulador` chama as mesmas funções
  puras do worker:
  - `CorrelacaoEmMemoria`, com a mesma chave, janela e recorrência;
  - `reavaliar`, que grava a decisão só quando a prioridade sobe;
  - `classificar` e `planejar`, com o silêncio por origem comparado à notificação mais grave.

  Sem banco: são 2,3 milhões de eventos, e o objetivo é medir as regras.
- **O simulador decide como o worker.** O teste
  `test_simulador_da_avaliacao_decide_como_o_worker` passa os mesmos 2.000 alertas do
  russellmitchell pelos dois caminhos e compara cada incidente (chave, prioridade e total) e o
  número de decisões: são iguais.
- **O relógio é o do evento.** Cinco dias de cenário passam por cinco noites de horário de silêncio
  e cinco resumos das 08:00. O despacho roda a cada minuto de relógio do evento; no worker, a cada
  5 s de relógio de parede.
- **O canal é falso** (`CanalFalso`). As mensagens são montadas pelos templates de verdade e
  guardadas; nada vai para o Telegram.
- **A política é a de demonstração, sem ajuste** ([`policies/avaliacao/ait-ads.yaml`](../policies/avaliacao/ait-ads.yaml)).
  Mudam só duas coisas:
  - **o inventário de cada cenário**, tirado do CSV (host → IP, um `/32` por host), com a
    criticidade por papel. Essa criticidade é **julgamento meu** (pendência A6):
    - **alta:** servidores e perímetro (intranet, web, mail, VPN, firewall);
    - **média:** compartilhamentos e DNS;
    - **baixa:** estações dos funcionários.
  - **o fuso:** Viena, onde fica o laboratório do AIT.
- **Os rótulos vêm do CSV dos autores**, casados pela posição e conferidos pelo horário a cada
  1.000 linhas. O `time_label` é a janela da fase; o `event_label` diz se o ataque causou o alerta.

## 2. Redução: eventos → incidentes → mensagens

| Cenário | Alertas | Eventos | Incidentes | Notificações | Só painel | Mensagens | P1/P2 | Resumos | Eventos/incidente | Eventos/mensagem |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fox | 462.523 | 451.439 | 1.946 | 1.376 | 580 | 39 | 33 | 6 | 232,0 | 11.575 |
| harrison | 583.754 | 516.343 | 1.734 | 1.408 | 333 | 64 | 58 | 6 | 297,8 | 8.068 |
| russellmitchell | 41.488 | 32.302 | 1.265 | 965 | 305 | 14 | 9 | 5 | 25,5 | 2.307 |
| santos | 126.513 | 82.401 | 374 | 153 | 226 | 31 | 26 | 5 | 220,3 | 2.658 |
| shaw | 68.539 | 51.831 | 2.436 | 1.851 | 590 | 18 | 11 | 7 | 21,3 | 2.880 |
| wardbeck | 88.204 | 63.694 | 3.231 | 2.707 | 530 | 63 | 57 | 6 | 19,7 | 1.011 |
| wheeler | 603.939 | 535.265 | 715 | 253 | 473 | 136 | 130 | 6 | 748,6 | 3.936 |
| wilson | 625.303 | 560.265 | 3.096 | 2.708 | 395 | 85 | 78 | 7 | 181,0 | 6.591 |
| **total** | **2.600.263** | **2.293.540** | **14.797** | **11.421** | **3.432** | **450** | **402** | **48** | **155,0** | **5.097** |

O que cada coluna conta:

- **eventos:** alertas convertidos. As 306.723 cópias do Suricata vindas do `fast.log` são
  descartadas.
- **notificações:** subidas para P1, P2 ou P3, as prioridades que a política avisa. Um incidente que
  subiu de P3 para P2 conta duas vezes.
- **só painel:** subidas para P4, que nunca notificam.
- **mensagens:** o que chegaria ao Telegram, depois do agrupamento do P2 e do resumo do P3.

As **14.853 decisões** gravadas são pouco mais que os incidentes: a decisão só é gravada quando a
prioridade sobe (ADR 0003). Se fosse gravada a cada evento, seriam 2,3 milhões.

**Espera, do registro ao envio:**

| Prioridade | Mediana | Máxima |
| --- | --- | --- |
| P1 | de 2 s a 36 s | 59 s |
| P2 | 10 min | 9 h 05 min |
| P3 | de 15 h 32 min a 18 h 15 min | 24 h |

- **P1** sai no despacho seguinte, inclusive de madrugada.
- **P2** espera os 10 min do agrupamento; de madrugada, espera o fim do horário de silêncio.
- **P3** espera o resumo das 08:00.

## 3. Cada fase do ataque gerou um incidente P1 ou P2?

Há três leituras possíveis, da mais frouxa à mais estrita:

- **Pela janela:** algum incidente P1/P2 tem um evento na janela da fase.
- **Pela causa:** algum incidente P1/P2 tem um evento que a fase causou.
- **Gerou:** o evento que levou o incidente a P1/P2 é da fase, e o ataque o causou.

A leitura estrita é a que responde à pergunta. **As outras duas enganam**, como mostra o harrison:

- o incidente de DNS `.biz` do firewall nasceu com o **primeiro evento** do cenário, já como P1, e
  nunca se encerrou (23.592 eventos em 5 dias);
- ele "contém" eventos causados pelas 9 fases, mas não foi gerado por nenhuma delas;
- ninguém recebe aviso novo quando essas fases acontecem.

A tabela usa esta legenda:

- ✅ gerou P1/P2;
- ↪ caiu num P1/P2 que já existia;
- ◌ P1/P2 só na janela, sem evento causado pelo ataque;
- P3: a fase foi vista, mas a prioridade não passou de P3;
- ✗ nenhum alerta causado pelo ataque;
- célula vazia: a fase não existe no cenário.

| Fase | fox | harrison | russellmitchell | santos | shaw | wardbeck | wheeler | wilson |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `network_scans` | ✗ | ↪ | ✗ | ✗ | ✗ | ✗ | ◌ | ✗ |
| `service_scans` | P3 | ↪ | P3 | P3 | ✗ | P3 | P3 | P3 |
| `wpscan` | ✅ | ✅ | P3 | ↪ | ✅ | ✅ | ✅ | ✅ |
| `dirb` | ↪ | ↪ | ✅ | ✅ | ↪ | ↪ | ✅ | ✅ |
| `webshell` |  | ↪ | ✗ | ✗ |  | ✗ | ✗ | ✗ |
| `cracking` | P3 | ↪ | ✗ | P3 | ✗ | ✗ |  | ✗ |
| `reverse_shell` |  | ↪ |  | ✗ | ✗ | ✗ | ✗ | ✗ |
| `privilege_escalation` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `service_stop` |  | ↪ |  |  |  |  |  |  |
| `dnsteal` | ◌ | ◌ | ✗ | ✗ | ✗ | ✗ | ◌ | ◌ |

Os 68 pares fase × cenário se dividem assim:

| Resultado | Pares | O que é |
| --- | ---: | --- |
| ✅ gerou P1/P2 | 18 | Escalada de privilégio em 8 de 8. Ataque web em 10 pares, e em todos os 8 cenários pelo menos um de `wpscan` ou `dirb` |
| ↪ caiu num P1/P2 que já existia | 11 | O segundo passo do ataque web entra no incidente `ataque_web` que o primeiro abriu (4 pares), o que está certo. Os outros 7 são do harrison, onde o incidente de `.biz` já era P1 antes do ataque |
| P3 | 9 | `service_scans` (6), `cracking` (2) e o `wpscan` do russellmitchell (1). As anomalias de protocolo ficam `desconhecido` (P3 base, pendência T2), e a política não leva `reconhecimento` além de P3 |
| ◌ só na janela | 5 | Coincidências: força bruta de usuários ou `.biz` que caíram na janela do `dnsteal` ou do `network_scans` |
| ✗ nenhum alerta causado | 25 | Nem o Wazuh nem o Suricata viram a fase |

**Nenhuma fonte viu 30 pares** (os 25 marcados com ✗ e os 5 só na janela). A **conclusão
honesta** é que a política da fase 2 não perde o que as fontes veem: dos 38 pares com alerta
causado pelo ataque, 29 terminaram em P1/P2 (18 gerados e 11 absorvidos), e os 9 restantes são
P3 por decisão da política.

O que as fontes, com as regras padrão, deixam de ver:

- **`dnsteal` nunca aparece como causa**, em nenhum cenário: o CSV não marca nenhum alerta como
  causado por ele (pendência D2);
- **`webshell`** e **`reverse_shell`** também ficam sem alerta causado, fora do harrison;
- **`network_scans`** fica sem alerta causado em 6 dos 8 cenários.

É o espaço do detector do TCC na fase 3.

## 4. Os P1 e P2 que acordariam alguém

| Cenário | P1 | P2 | P3 | P4 | P1/P2 pela causa | P1/P2 só na janela | P1/P2 fora de ataque |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fox | 5 | 28 | 1.340 | 573 | 2 | 1 | 30 |
| harrison | 4 | 54 | 1.347 | 329 | 2 | 5 | 51 |
| russellmitchell | 4 | 5 | 954 | 302 | 2 | 0 | 7 |
| santos | 6 | 20 | 125 | 223 | 2 | 0 | 24 |
| shaw | 2 | 9 | 1.837 | 588 | 2 | 0 | 9 |
| wardbeck | 5 | 55 | 2.646 | 525 | 3 | 0 | 57 |
| wheeler | 118 | 12 | 119 | 466 | 3 | 5 | 122 |
| wilson | 9 | 74 | 2.623 | 390 | 3 | 2 | 78 |
| **total** | **153** | **257** | **10.991** | **3.396** | **19** | **13** | **378** |

As colunas "pela causa", "só na janela" e "fora de ataque" classificam **o evento que levou o
incidente a P1/P2**.

Por categoria, a mesma classificação:

| Categoria | Pela causa | Só na janela | Fora de ataque | De onde vem o ruído |
| --- | ---: | ---: | ---: | --- |
| `forca_bruta` (P2) | 3 | 8 | **246** | Falhas de login de usuários no `mail` (Dovecot 9705, PAM 5503, syslog 2501) e logins no WordPress da intranet (31509). A recorrência ≥ 5 sobe a urgência, e o ativo é de criticidade alta |
| `exfiltracao` (P1) | 0 | 5 | **122** | `ET INFO Observed DNS Query to .biz TLD` (sid 2027863), 108 deles no wheeler |
| `comprometimento` (P1) | 8 | 0 | **10** | `sudo` de rotina de administradores (`First time user executed sudo`, `Successful sudo to ROOT`) |
| `ataque_web` (P1) | 8 | 0 | 0 | — |

Cada P1/P2 fora de ataque vira uma mensagem urgente. São 402 mensagens P1/P2 em 39,7 dias de
laboratório, **10 por dia**, e 9 em cada 10 incidentes P1/P2 subiram fora de ataque. É a fadiga que o Ronda existe para
evitar, e o que decide isso é a política, não o código (pendências A1, A2 e A5).

## 5. O que não funcionou como esperado

- **O silêncio por origem não suprimiu nada** em 2,3 milhões de eventos. O motivo:
  - o silêncio só vale dentro de `silencio_por_origem` (30 min) depois da notificação anterior;
  - para nascer um incidente novo da mesma chave, a chave precisa ficar 30 min sem evento,
    porque a janela da correlação também é 30 min;
  - então a notificação anterior sempre tem pelo menos esse tempo.

  Com os dois valores iguais, a regra é inerte (pendência A3). O teste
  `test_silencio_por_origem_so_age_quando_e_maior_que_a_janela` fixa esse comportamento.
- **O resumo diário não escala.** São 10.991 incidentes P3 em 48 resumos, uma média de 229 por
  mensagem, cortados no limite de 4.096 caracteres do Telegram.
  - **Quase todos são `desconhecido` do Suricata**, as anomalias de protocolo da pendência T2.
    Foram 97% a 99% do P3 em russellmitchell, harrison, fox e wilson.
  - **Eles se fragmentam:** o destino fora do inventário entra na chave pelo IP, e cada IP externo
    abre o seu incidente. Nesses quatro cenários, 92% a 97% desses incidentes têm um IP como
    ativo; no russellmitchell, são 938 incidentes em 606 chaves (pendência A4).
  - **O wheeler é a exceção:** tem 94 incidentes desse tipo, em 5 chaves.
- **Defeito encontrado e corrigido: o adaptador do Wazuh não usava o `agent.ip`.**
  - O AIT-ADS chama todos os agentes de `wazuh-client`, e o `predecoder.hostname` falta em cerca
    de 60% dos alertas.
  - Sem o IP do agente, o inventário não achava a máquina, e alertas de máquinas diferentes
    caíam na mesma chave `wazuh-client`.
  - Agora, sem `dstip`, o destino é o agente.
  - Os testes do adaptador cobrem a regra e o caso do manager sem IP.

## 6. Limites desta avaliação

- **Não há reconhecimento.** Ninguém clica em "Reconhecer", então o efeito do reconhecimento no
  ciclo de vida não foi medido.
- **A criticidade dos ativos é minha** (A6). Com a intranet em média, por exemplo, o P2 de força
  bruta dela cairia para P3.
- **O despacho a cada minuto de relógio do evento** arredonda as esperas para o minuto. A ordem e
  o agrupamento são os mesmos do worker.
- **Um tenant por cenário.** Nada aqui mede isolamento entre tenants, que a fase 2 cobre nos
  testes de integração (RLS).

## 7. Como reproduzir

```sh
uv sync --extra notebooks
uv run jupyter nbconvert --to notebook --execute notebooks/02_avaliar_fase2.ipynb --output-dir /tmp
```

A execução leva cerca de 12 minutos. O fox, o harrison, o wheeler e o wilson levam de 2 a 3
minutos cada, por causa das 400 mil linhas do `dirb`.
