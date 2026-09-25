# ADR 0001 — Regras do motor para lacunas da política

- **Data:** 2026-09-25
- **Estado:** aceita

## Contexto

A política de exemplo da especificação não cobria toda a taxonomia (faltavam `ataque_web`,
`reconhecimento` e `benigno`) e não dizia o que fazer com ativo fora do inventário, com
modificador que ultrapassa a escala nem com prioridade sem prazo. O motor precisa ser
determinístico e explicável em todos esses casos.

## Decisão

1. **Categoria sem regra de impacto ou urgência** usa a prioridade base da taxonomia
   (herdada do TCC), e o rastro registra o que faltou. A política continua mandando sempre
   que tem regra.
2. **Ativo fora do inventário** recebe `criticidade_padrao` da política (padrão `media`).
3. **Resolução do ativo:** nome informado pela fonte, depois IP de destino, depois IP de
   origem. A origem cobre máquina interna comprometida falando com a internet. Entre redes
   sobrepostas, vence a mais específica.
4. **Modificadores** aplicam-se na ordem do arquivo e param nas pontas da escala. Um ajuste
   sem efeito é registrado no rastro.
5. **Prioridade sem prazo** em `resposta` é válida e aparece como "sem prazo de resposta".
6. **Linhas de impacto incompletas e matriz incompleta** são erro de validação. Uma lacuna
   aí seria ambígua, ao contrário de uma categoria inteira ausente.
7. **Condições dos modificadores** são comparações simples sobre campos conhecidos do
   contexto, interpretadas sem `eval`.

## Consequências

Uma política mínima (só `tenant`, `versao` e `matriz`) já funciona e reproduz a
priorização do TCC. As lacunas nunca derrubam a avaliação e sempre ficam visíveis no rastro.
