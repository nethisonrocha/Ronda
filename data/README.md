# data/

Datasets do projeto. **Esta pasta fica fora do git**: só este README e o manifesto
[`datasets.yaml`](datasets.yaml) são versionados. Isso tem três motivos:

- **Tamanho.** Os datasets de fluxo passam de gigabytes.
- **Licença.** O uso comercial dos NetFlow da UQ exige acordo com os autores, e a licença do AIT-ADS precisa ser conferida no Zenodo antes de qualquer redistribuição.
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

## Datasets

| Chave | Uso | Download | Licença |
| --- | --- | --- | --- |
| `ait-ads` | avaliação da governança, tradutor | automático | a conferir no Zenodo |
| `cic-ids2017` | detector (base do TCC) | manual | a conferir |
| `cic-ids2017-improved` | detector, versão corrigida | automático | a conferir |
| `netflow-v3` | detector, generalização | automático | uso comercial exige acordo |
| `bccc` | detector | automático | a conferir |

Citações e URLs estão no manifesto, e os campos ainda não conferidos estão como `null`.
