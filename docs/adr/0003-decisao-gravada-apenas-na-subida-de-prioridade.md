# ADR 0003 — Gravação de decisão apenas na subida monotônica de prioridade

- **Data:** 2026-11-23
- **Estado:** aceita

## Contexto

Durante varreduras ou ataques volumétricos, um único incidente correlacionado pode receber centenas ou milhares de eventos em sequência (ex.: 380 mil eventos de um scan ou força bruta). Reavaliar a prioridade em memória quando o contexto muda é barato, mas gravar uma nova linha na tabela imutável `decisoes` (e reavaliar envio de notificação) para cada evento redundante poluiria o histórico de auditoria e causaria fadiga de alertas.

Além disso, um incidente não deve cair de prioridade automaticamente apenas porque um evento posterior dentro da mesma janela teve contexto menos grave (monotonicidade da severidade do incidente ativo).

## Decisão

1. **Prioridade monotônica:** ao reavaliar um incidente ativo, a prioridade efetiva é o máximo de gravidade entre a prioridade atual do incidente e a nova decisão do `Motor` (`elevar(prioridade_atual, decisao.prioridade)`).
2. **Persistência seletiva:** a decisão e o registro de auditoria (`incidente.priorizado`) só são gravados no banco — e o roteador de notificações só é acionado — quando `reav.subiu` é verdadeiro (ou seja, no nascimento do incidente ou quando a prioridade efetiva sobe, por exemplo de P3 para P2 ou de P2 para P1).

## Consequências

- O histórico em `decisoes` registra apenas as transições significativas de severidade do incidente, mantendo o rastro auditável conciso e legível para operadores.
- O consumo de espaço e escrita no PostgreSQL cai drasticamente em cenários de rajadas de eventos repetitivos.
