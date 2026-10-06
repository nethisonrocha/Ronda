# data/

Datasets do projeto. **Esta pasta fica fora do git**: só este README e o manifesto
[`datasets.yaml`](datasets.yaml) são versionados. Isso tem três motivos:

- **Tamanho.** Os datasets de fluxo passam de gigabytes.
- **Licença.** O uso comercial dos NetFlow da UQ exige acordo com os autores, e os CIC não publicam licença nenhuma (veja a tabela abaixo).
- **Reprodutibilidade.** Quem clona o repositório baixa exatamente a versão registrada no manifesto, com checksum conferido.

## Como obter

```sh
make data                      # todos
make data DATASET=ait-ads      # só um
uv run python scripts/download_data.py --list
```

Os notebooks do Colab rodam o mesmo script na primeira célula.

Datasets marcados como `download: manual` exigem cadastro ou acordo. Nesse caso, o script
informa a página e o caminho onde colocar o arquivo, e depois confere o checksum.

## Layout

```
data/
├── datasets.yaml       manifesto: URL, versão, checksum, licença
├── raw/<dataset>/      exatamente como baixado, nunca editado
├── interim/            convertido para Parquet, no esquema único
└── processed/
    ├── governance-eval/   AIT-ADS normalizado e rotulado, para avaliar o motor
    ├── detector/          features prontas para o treino
    └── translator/        pares incidente → explicação (fase 4)
```

## Regras

- **`raw/` é somente leitura.** Toda transformação grava um arquivo novo em `interim/` ou
  `processed/`. Qualquer resultado pode ser refeito do zero, e os erros de pré-processamento,
  como os conhecidos do próprio CIC-IDS2017, ficam rastreáveis.
- **Use Parquet a partir de `interim/`.** Os CSVs de fluxo são grandes e lentos de carregar.
- **Os containers nunca embutem dados.** No Compose, `data/` entra como volume, e a demo
  pública usa só `samples/`.
- **`samples/` e `tests/fixtures/` são versionados.** Por isso, só recebem trechos pequenos
  cuja licença permite redistribuição, ou alertas gerados por nós com IPs anonimizados.
- **Dataset derivado herda a licença.** O dataset do tradutor (fase 4) deriva do AIT-ADS. Se for publicado no Hugging Face Hub, a licença precisa ser compatível com a do original.

### Trechos do AIT-ADS em `samples/` (pendência D4, 06/10/2026)

O mesmo alerta existe sob duas licenças, conforme a fonte de onde é copiado. Não é parecer
jurídico; é o que as duas licenças pedem.

- **JSON e `labels.csv` do Zenodo: CC BY 4.0.** Trechos podem entrar em `samples/`, inclusive
  para uso comercial, com atribuição: autores (Landauer, Skopik, Wurzenberger / AIT), DOI
  10.5281/zenodo.8263181, link para a licença e o que foi alterado (recorte, IPs anonimizados).
  Os trechos continuam CC BY 4.0 e não mudam a licença Apache-2.0 do código. Ponha a atribuição
  num `NOTICE` ou num `README` da pasta.
- **CSV do GitHub do AIT (`alerts_csv`): GPL-3.0.** Um trecho precisaria continuar GPL-3.0, numa
  pasta própria com o `LICENSE` da GPL e o aviso de origem (commit `5459b57`). A leitura usual é
  que um arquivo de dados lido por testes é um "agregado" e não torna o código GPL, mas isso não
  é pacífico: a GPL foi escrita para software.
- **Regra do projeto:** fixtures e amostras saem **dos JSON do Zenodo**, com os rótulos gerados
  pelo código do próprio Ronda a partir do `labels.csv`. Nada do CSV GPL entra no repositório.

## Datasets

| Chave | Uso | Download | Licença |
| --- | --- | --- | --- |
| `ait-ads` | avaliação da governança, tradutor (JSON e `labels.csv` do Zenodo, em `raw/ait-ads/json/`) | automático | CC BY 4.0 |
| `ait-ads-csv` | avaliação da governança (CSV do GitHub do AIT, em `raw/ait-ads/csv/`) | automático | GPL-3.0 (repositório) |
| `cic-ids2017` | detector (base do TCC) | manual (formulário da UNB) | nenhuma publicada; "para pesquisadores", com citação |
| `cic-ids2017-improved` | detector, versão corrigida (WTMC2021) | automático | nenhuma publicada |
| `netflow-v3` | detector, generalização (NF-CSE-CIC-IDS2018-v3) | manual (UQ RDM) | uso comercial exige acordo |
| `bccc` | detector | manual (formulário) | a definir: ainda não se sabe qual dataset do BCCC é |

Citações, URLs e checksums estão no manifesto, conferidos nas páginas oficiais em 06/10/2026.
Os campos que continuam `null` não puderam ser confirmados (estão atrás de formulário, ou o
pacote não está na máquina).
