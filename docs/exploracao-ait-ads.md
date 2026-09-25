# Exploração do AIT-ADS

- **Data:** 2026-09-25
- **Notebook:** [`notebooks/01_explorar_ait_ads.ipynb`](../notebooks/01_explorar_ait_ads.ipynb)
- **Rascunho da taxonomia:** [`taxonomia-rascunho.csv`](taxonomia-rascunho.csv)
- **Estado:** proposta de taxonomia **aguardando aprovação**

O objetivo foi entender os alertas do Wazuh e do Suricata no AIT Alert Data Set para definir as
categorias internas do Ronda e o mapeamento de fases de ataque e assinaturas para elas. A análise
usou o cenário **russellmitchell**, a validação usou o **fox**, e a cobertura foi checada nos
CSVs dos oito cenários.

## 1. O que os dados são de verdade

| Hipótese do plano | O que os dados mostram |
| --- | --- |
| JSON exportado do Elasticsearch, com o alerta em `_source` | **JSON Lines, um alerta do Wazuh por linha, na raiz**, sem envelope |
| Os arquivos do Wazuh contêm os alertas do Suricata | Sim, mas **cada alerta do Suricata aparece duas vezes** (1.3) |
| `time_label` indica se o alerta é de ataque | Indica só a **janela de tempo**; o que o alerta causou está em `event_label` (1.2) |

### 1.1 Estrutura (russellmitchell)

- **CSV:** 45.544 alertas, de 21/01/2022 00:00:01 a 24/01/2022 23:39:13 (UTC). Nenhum valor
  faltante. Por ferramenta: Wazuh 32.302, Suricata 9.186 e AMiner 4.056 (descartado).
- **JSON do Wazuh:** 41.488 linhas, que é exatamente o número de alertas Wazuh + Suricata do
  CSV. Os 14 campos a seguir estão presentes em todos os alertas: `@timestamp`, `id`,
  `location`, `rule.{id, description, level, groups, firedtimes, mail}`, `agent.{id, name, ip}`,
  `manager.name` e `input.type`. Ao todo há 119 caminhos de chave, quase todos opcionais e
  específicos de decoder.
- **Alerta do Suricata**, dentro do do Wazuh (decoder `json`, regra 86601,
  `location = /var/log/suricata/eve.json`):
  - `data.alert.{signature, signature_id, category, severity}` e
    `data.{src_ip, dest_ip, dest_port, proto}` estão sempre presentes;
  - `data.alert.metadata.former_category` aparece só em parte deles.
- **IPs nos alertas do Wazuh:** o `ip_origem` aparece em 34% deles e o `ip_destino` em 0,4%. Na
  prática, **o ativo do Wazuh é o agente** (`agent.ip`, `agent.name`).
- **Achatado:** o Parquet reduz o volume de 45 MB para 327 KB no russellmitchell e de 491 MB
  para 1,0 MB no fox (`data/interim/ait-ads/`, fora do git).

### 1.2 Os dois rótulos

Segundo o `analyze.py` dos autores:

- **`time_label`** é a fase do ataque em cuja janela o alerta caiu, ou `false_positive` fora de
  qualquer janela. Um alerta de rotina que ocorre durante um ataque herda a fase.
- **`event_label`** é o rótulo por evento, vindo das linhas de log e dos fluxos rotulados. Vale
  `-` quando o ataque não causou o alerta.

O exemplo mais claro é o `9701 Dovecot Authentication Success`, com 375 ocorrências dentro da
janela do `dnsteal` e **nenhuma** causada pelo ataque. A classificação por janela pedida no
plano foi mantida, e a contagem de `event_label` foi acrescentada a ela como evidência.

**Junção CSV ↔ JSON.** Filtrando o CSV sem o AMiner, a linha *i* do CSV corresponde ao alerta *i*
do JSON, porque o `analyze.py` escreve na mesma ordem. O notebook confere horário, descrição e IP
linha a linha: **100% de concordância** no russellmitchell (41.488 linhas) e no fox (462.523).

### 1.3 Suricata duplicado

O Wazuh lê o Suricata por dois caminhos:

- o `eve.json`, pela regra **86601**, que traz o alerta completo;
- o `fast.log`, pelo decoder `snort`, que gera as regras **20100, 20101, 20151, 20152, 20161 e
  20162**.

A regra 20161 só aparece nos outros cenários e foi confirmada no JSON do harrison. No
russellmitchell, as regras do `fast.log` somam 9.186 alertas, exatamente o número de alertas do
`eve.json`, e todos os `sid` do `fast.log` existem no `eve.json`. O CSV dos autores conta essas
cópias como alertas do Wazuh (`W-All-Evt`, `W-All-Ids`, `W-All-Mul*`).

**Consequência para o Ronda:** o adaptador do Wazuh precisa **descartar as regras 201xx vindas do
`fast.log`** quando o Suricata também chega pelo `eve.json`. Sem isso, cada evento vira dois e o
volume do Suricata dobra. No rascunho, essas regras aparecem com `classificacao = duplicata`.

## 2. Volume e ruído

Contagens sem AMiner e sem as cópias do `fast.log`:

| | russellmitchell | fox |
| --- | ---: | ---: |
| Wazuh | 23.116 | 440.355 |
| Suricata | 9.186 | 11.084 |
| Cópias do `fast.log` (descartadas) | 9.186 | 11.084 |
| Wazuh fora das janelas de ataque | 64,9% | 6,5% |
| Wazuh não causado pelo ataque | 67,0% | 6,8% |
| Suricata fora das janelas de ataque | 97,7% | 96,9% |
| Suricata não causado pelo ataque | 99,5% | 99,7% |

- **O Suricata é quase só ruído** nos dois cenários. Os TLS inválidos (`SURICATA TLS invalid
  record/traffic` e `invalid handshake message`) respondem por 96% do volume dele.
- **A taxa de ruído do Wazuh depende do tamanho do ataque, não do detector.** No fox, o dirb gera
  406 mil alertas, e só o `31101 Web server 400 error code` responde por 380 mil (82%). A taxa
  agregada cai para 6,5%, mas o ruído de fundo continua igual. Por isso, a análise que vale é
  **por assinatura**.
- **Maiores fontes de ruído:**
  - `9701 Dovecot Authentication Success`: 14 mil no russellmitchell e 28 mil no fox;
  - TLS inválido do Suricata;
  - `52507 ClamAV database update`;
  - `ET POLICY … APT User-Agent`.

## 3. Assinaturas × ataques

Foram 33 assinaturas no russellmitchell e 38 no fox; 32 são comuns aos dois, e a união tem 39.
Classificação por janela de tempo:

| | russellmitchell | fox |
| --- | ---: | ---: |
| só em ataques | 16 | 11 |
| ambos | 7 | 15 |
| só ruído | 10 | 12 |

Padrões que se repetem nos dois cenários:

- **As varreduras web são o grosso dos alertas de ataque.** Aparecem em `31101`, `31151`, `30305`,
  `30306`, `31516` e `31104`, sempre nas fases `dirb` e `wpscan`.
- **A varredura de serviços** aparece em `ET SCAN Possible Nmap User-Agent`, `5706 sshd: insecure
  connection attempt` e em anomalias de protocolo do Suricata (SMTP e TLS SSLv2) que o nmap
  provoca.
- **A escalada de privilégio** aparece em `5402 sudo to ROOT`, `5304 changed UID` e nas sessões PAM
  (`5501`/`5502`), que o `event_label` liga a `escalated_sudo_command` e
  `attacker_change_user`.
- **Nenhum alerta de força bruta do Wazuh foi causado por ataque.** São eles `9705`, `2501`, `5503`,
  `5551` e `9751` (este último, "Dovecot brute force attack"). No fox, alguns caem na janela do
  `cracking`, mas com zero eventos de ataque.

## 4. Taxonomia proposta

### 4.1 Categorias

| Categoria | Significado | Situação |
| --- | --- | --- |
| `reconhecimento` | Varreduras de rede, serviço e aplicação web | existente |
| `ataque_web` | Exploração de aplicação web (injeção, webshell) | existente |
| `forca_bruta` | Tentativas repetidas de autenticação, quebra de senhas | existente |
| `comprometimento` | Execução no host: shell reverso, escalada de privilégio | existente |
| `negacao_servico` | Indisponibilidade provocada: parada de serviço, DoS | existente |
| `exfiltracao` | Saída de dados, como o túnel DNS | **nova** |
| `benigno` | Atividade legítima **pela semântica** do alerta | existente |
| `desconhecido` | Sem regra de mapeamento ou sem semântica de ataque | **nova** |

**`exfiltracao` entra.** O `dnsteal` é uma fase própria em todos os cenários, e a exfiltração tem
impacto diferente dos outros ataques (confidencialidade). A evidência decisiva está na seção 7 do
notebook: o `ET INFO Observed DNS Query to .biz TLD` é o alerta que dispara com o dnsteal em
harrison (47.183) e santos (25.707), e soma 72.890 eventos de ataque. No russellmitchell e no fox
ele é "só ruído", porque o atacante usou outro domínio.

**`benigno` descreve o que o alerta diz, não quanto ele é barulhento.** Assinaturas "só ruído"
ficam com a categoria da sua semântica e entram na lista de candidatas a ajuste de política
(4.4). O caso do `.biz` mostra o risco de fazer o contrário: um alerta que é ruído num ambiente é
o detector de exfiltração em outro.

### 4.2 Fase → categoria

| Fase | Categoria |
| --- | --- |
| `network_scans`, `service_scans`, `wpscan`, `dirb` | `reconhecimento` |
| `webshell` | `ataque_web` |
| `cracking` | `forca_bruta` |
| `reverse_shell`, `privilege_escalation` | `comprometimento` |
| `service_stop` | `negacao_servico` |
| `dnsteal` | `exfiltracao` |
| `false_positive` | sem categoria: fora de ataque |

### 4.3 Assinatura → categoria

Regras em ordem de preferência. As estruturadas vêm primeiro, e o texto da descrição nunca é
usado.

1. **Exceções por regra ou assinatura**, cada uma com motivo:
   - `31101` (400 error) → `reconhecimento`: tem o grupo `attack`, mas 99,99% das ocorrências
     vêm do dirb/wpscan;
   - `31509` (login no CMS) → `forca_bruta`, apesar dos grupos `appsec|attack`;
   - `52507` (ClamAV) → `benigno`, apesar do grupo `virus`: é a atualização de rotina, nível 3;
   - `5502` (fim de sessão PAM) → `benigno`;
   - `31122` (erro 500) e `80730` (SELinux) → `desconhecido`;
   - `ET INFO Observed DNS Query to .biz TLD` → `exfiltracao`.
2. **Wazuh, primeiro grupo que casar:**
   - `sudo`, `su` → `comprometimento`;
   - `authentication_failed`, `authentication_failures`, `invalid_login` → `forca_bruta`;
   - `web_scan`, `recon`, `access_denied` → `reconhecimento`;
   - `attack` → `ataque_web`;
   - `authentication_success` → `benigno`;
   - sem grupo mapeado → `desconhecido`.
3. **Suricata, família ET da assinatura** (convenção estruturada do Emerging Threats):
   - `ET SCAN` → `reconhecimento`;
   - `ET POLICY` → `benigno`.
4. **Suricata, categoria:**
   - `Not Suspicious Traffic` → `benigno`;
   - `Web Application Attack` → `ataque_web`;
   - `Generic Protocol Command Decode` e `Potentially Bad Traffic` → `desconhecido`.
5. **Regras 201xx do `fast.log`:** duplicata, descartar na ingestão.

Resultado nas 39 assinaturas: reconhecimento 6, ataque_web 2, forca_bruta 6, comprometimento 3,
exfiltracao 1, benigno 6 e desconhecido 15.

### 4.4 Candidatas a ajuste de política

Estas são assinaturas "só ruído", ou "ambos" sem nenhum evento de ataque. A política do tenant
pode rebaixar a urgência delas, mas não mudar sua categoria.

| Categoria | Assinaturas |
| --- | --- |
| `forca_bruta` | 9705, 2501, 5503, 5551, 9751, 31509 |
| `benigno` | 9701, 5715, 52507, ET POLICY APT |
| `desconhecido` | TLS inválido, HTTP gzip e chunk, SELinux 80730, DNS para `.cloud`, `.to` e `.ga` |
| `comprometimento` | 5403 (primeiro sudo de um usuário; 2 ocorrências, ruído no fox) |
| `exfiltracao` | `.biz`: ruído aqui, detector de exfiltração em harrison e santos |

## 5. Validação no fox: divergências

- **Mudanças de classificação** em 8 das 32 assinaturas comuns. Em todas, a categoria se manteve:
  - `31101`, `31122` e `5402` passam de "só em ataques" para "ambos", com poucas ocorrências
    fora da janela (8, 16 e 1);
  - `9705`, `5503` e `2501` passam de "só ruído" para "ambos", porque caem na janela do
    `cracking`, mas continuam com **zero** eventos de ataque;
  - `ET INFO .cloud` passa de "só ruído" para "ambos" (1 na janela do `dnsteal`, 0 eventos);
  - `SURICATA HTTP invalid response chunk len` passa de "só em ataques" para "só ruído" (1
    ocorrência em cada cenário).
- **Assinaturas novas no fox (6):**
  - `31509` (CMS login) e `5551` (PAM, várias falhas) → `forca_bruta`;
  - `5403` (primeiro sudo) → `comprometimento`;
  - DNS para `.to` e `.ga` e SNI `.ga` → `desconhecido`.
- **Só no russellmitchell (1):** `SURICATA TLS invalid record type`.
- **O dirb domina o fox.** A proporção de ruído por ferramenta muda muito entre os cenários (2),
  e por isso **métrica de redução de ruído precisa ser por assinatura, ou normalizada por ataque**.
- **Mapeamento contra a fase dominante.** As mesmas divergências aparecem nos dois cenários e
  estão na lista de decisões (6).

## 6. Decisões em aberto

1. **`31104 Common web attack` e `31516 Suspicious URL access`.** Proponho `ataque_web`, pelo
   grupo `attack`. Nos dados, 100% das ocorrências vêm do dirb, portanto seriam `reconhecimento`.
   Mantive `ataque_web` porque a categoria descreve o que o alerta afirma, e agrupar a varredura
   é papel da correlação. O custo é que, sem correlação, o dirb do fox geraria 644 alertas de
   `ataque_web`.
2. **Anomalias de protocolo do Suricata que só aparecem na varredura de serviços** (SMTP invalid
   reply e no welcome, TLS SSLv2 header, HTTP chunk len). Proponho `desconhecido`, pela categoria
   `Generic Protocol Command Decode`. Pelos dados seriam `reconhecimento`, mas são poucas
   ocorrências (≤ 4 por cenário).
3. **Sessões PAM (`5501`, `5502`).** Proponho `benigno`. Elas aparecem na escalada de privilégio,
   mas são mais frequentes como rotina. O sinal de ataque vem da combinação com `5402`/`5304`,
   o que é trabalho da correlação.
4. **Família de consultas DNS a TLDs suspeitos** (`.cloud`, `.to`, `.ga`, `.cc`, `.pw`, `.su`).
   Proponho `desconhecido` para todas, menos a `.biz`, que tem evidência de exfiltração. A
   alternativa é mapear a família inteira para `exfiltracao`.
5. **`sudo`/`su` → `comprometimento`.** Esse mapeamento acerta nos dados, mas o sudo legítimo de
   administradores precisa de ajuste por ativo na política (`5403` foi ruído no fox).
6. **Prioridade base das categorias novas.** Sugiro `exfiltracao` = P1, como `comprometimento`,
   e `desconhecido` pela urgência padrão da política (etapa 3).

## 7. Dúvidas e limitações

- **Cobertura de detecção.** Em todos os oito cenários, **nenhum alerta Wazuh/Suricata é
  causado** por `webshell`, `reverse_shell` ou `service_stop`. Esses eventos só aparecem no AMiner
  (`webshell_cmd` 25, `crack_passwords` 11). O `cracking` aparece apenas em 6 alertas do Suricata
  (`online_cracking`). O mapeamento de fase dessas categorias fica sem assinatura correspondente
  nestes dados.
- **O `.biz` no wheeler:** são 18.838 ocorrências, todas com `event_label = -`, e a janela do
  `dnsteal` no wheeler tem só 466 alertas. Pode ser ruído real ou rotulagem incompleta; não
  investiguei.
- **Cenários não analisados a fundo.** Nos outros seis cenários, 15 assinaturas não aparecem no
  russellmitchell nem no fox. As principais são `ET DNS Query for .cc TLD`, `ET HUNTING …
  COVID-19`, `ET INFO TLS Handshake Failure`, STUN, `.pw`, `.su`, `ET SCAN … Port 445`, `CMS …
  brute force attempt` e a regra `20161`. Pelas regras acima, cairiam em `desconhecido`,
  `reconhecimento` (`ET SCAN`), `forca_bruta` (CMS brute force) e duplicata (`20161`).
  Precisam de revisão antes do adaptador.
- **O ativo do Wazuh é o agente.** Os IPs de origem e destino são raros nos alertas do Wazuh. A
  resolução de ativo por IP de destino (etapa 4) quase só funciona para o Suricata; para o Wazuh,
  o adaptador deve informar o **nome do ativo**, a partir de `agent.name`/`predecoder.hostname`.
- **AMiner fora do escopo.** Ele é o único detector que enxerga webshell, shell reverso e parte
  da exfiltração. É candidato a fonte numa fase futura.
