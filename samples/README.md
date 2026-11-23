# Amostras para demonstração (`samples/`)

Arquivos pequenos e versionados com alertas reais extraídos do **AIT Alert Data Set (AIT-ADS)** para demonstrações e testes de replay sem baixar o conjunto completo.

## Conteúdo

- `demo_wazuh.jsonl`: 151 alertas do cenário `russellmitchell` (Wazuh JSON Lines), cobrindo eventos benignos, ruído (`desconhecido`), força bruta, reconhecimento, ataque web e comprometimento.
- `demo_suricata.jsonl`: 35 alertas no formato nativo `eve.json` do Suricata (`event_type: "alert"`), extraídos dos campos `data.alert` do mesmo recorte.

## Licença e atribuição (CC BY 4.0)

Os dados originais foram extraídos dos arquivos JSON publicados no Zenodo sob licença **Creative Commons Attribution 4.0 International (CC BY 4.0)** — <https://creativecommons.org/licenses/by/4.0/> (conforme regra D4 em [`data/README.md`](../data/README.md)):

- **Autores:** Max Landauer, Florian Skopik, Markus Wurzenberger (AIT Austrian Institute of Technology).
- **Fonte:** AIT Alert Data Set (AIT-ADS), Zenodo, DOI `10.5281/zenodo.8263181` (<https://zenodo.org/records/8263181>).
- **Citação:** Landauer, Skopik e Wurzenberger. *Introducing a New Alert Data Set for Multi-Step Attack Analysis*. CSET 2024, pp. 41–53. DOI `10.1145/3675741.3675748`.
- **Alterações realizadas:** recorte de subconjunto representativo de `russellmitchell_wazuh.json` (`demo_wazuh.jsonl`) e extração dos objetos `data.alert` para o formato nativo `eve.json` (`demo_suricata.jsonl`).
