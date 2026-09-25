"""Adaptador do Wazuh: alerta do Wazuh (e do Suricata lido pelo Wazuh) → `Evento`.

Formatos aceitos, todos com o mesmo objeto de alerta do Wazuh:

- **AIT-ADS** e **alerts.json**: um alerta por linha (JSON Lines), veja `iterar_jsonl`;
- **webhook** (integração do Wazuh com `alert_format json`): o alerta no corpo do POST;
- **indexador** (Wazuh indexer / OpenSearch): o alerta dentro de `_source`.

O horário vem de `@timestamp` (indexador, AIT-ADS) ou de `timestamp` (alerts.json, webhook,
no formato `2022-01-21T00:02:27.000+0000`).

A categoria sai de `mapping.yaml`, que é gerado a partir da taxonomia. Um alerta sem
correspondência vira `desconhecido`, e o caminho da decisão fica em
`evidencias["mapeamento"]`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from datetime import datetime
from enum import StrEnum
from importlib import resources
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from typing import Any, NamedTuple
from uuid import NAMESPACE_URL, UUID, uuid5

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ronda.adapters.base import AlertaInvalido
from ronda.domain.event import Evento
from ronda.domain.taxonomy import Categoria

# Espaço de nomes dos ids determinísticos: o mesmo alerta sempre gera o mesmo Evento.id.
NAMESPACE_RONDA = uuid5(NAMESPACE_URL, "https://github.com/nethisonrocha/Ronda/eventos")


# --- mapeamento --------------------------------------------------------------------------


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _RegraDeGrupo(_Estrito):
    grupo: str
    categoria: Categoria


class _Descartar(_Estrito):
    regras_fastlog: list[str] = Field(default_factory=list)


class _Wazuh(_Estrito):
    regras: dict[str, Categoria] = Field(default_factory=dict)
    grupos: list[_RegraDeGrupo] = Field(default_factory=list)


class _Suricata(_Estrito):
    assinaturas: dict[str, Categoria] = Field(default_factory=dict)
    familias_et: dict[str, Categoria] = Field(default_factory=dict)
    categorias: dict[str, Categoria] = Field(default_factory=dict)


class Via(StrEnum):
    exata = "exata"
    """Regra do Wazuh ou assinatura do Suricata listada na taxonomia."""
    generica = "generica"
    """Grupo do Wazuh, família ET ou categoria do Suricata."""
    sem_mapeamento = "sem_mapeamento"
    """Nada casou: vira desconhecido."""


class Classificacao(NamedTuple):
    categoria: Categoria
    via: Via
    chave: str
    """O que casou, ex. "wazuh.grupos:sudo"; ou o que foi procurado, se nada casou."""


class Mapeamento(_Estrito):
    versao: int
    taxonomia: str
    descartar: _Descartar = Field(default_factory=_Descartar)
    wazuh: _Wazuh = Field(default_factory=_Wazuh)
    suricata: _Suricata = Field(default_factory=_Suricata)

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> Mapeamento:
        """O mapping.yaml do pacote, ou outro arquivo no mesmo formato."""
        if caminho is None:
            texto = resources.files(__package__).joinpath("mapping.yaml").read_text("utf-8")
        else:
            texto = caminho.read_text(encoding="utf-8")
        return cls.model_validate(yaml.safe_load(texto))

    def classificar_wazuh(self, regra_id: str, grupos: list[str]) -> Classificacao:
        if regra_id in self.wazuh.regras:
            return Classificacao(self.wazuh.regras[regra_id], Via.exata, f"wazuh.regras:{regra_id}")
        conjunto = set(grupos)
        for regra in self.wazuh.grupos:
            if regra.grupo in conjunto:
                return Classificacao(regra.categoria, Via.generica, f"wazuh.grupos:{regra.grupo}")
        return Classificacao(Categoria.desconhecido, Via.sem_mapeamento, f"wazuh.regras:{regra_id}")

    def classificar_suricata(self, assinatura: str, categoria: str | None) -> Classificacao:
        if assinatura in self.suricata.assinaturas:
            return Classificacao(
                self.suricata.assinaturas[assinatura],
                Via.exata,
                f"suricata.assinaturas:{assinatura}",
            )
        partes = assinatura.split(" ")
        if len(partes) > 1 and partes[0] == "ET" and partes[1] in self.suricata.familias_et:
            return Classificacao(
                self.suricata.familias_et[partes[1]],
                Via.generica,
                f"suricata.familias_et:{partes[1]}",
            )
        if categoria in self.suricata.categorias:
            return Classificacao(
                self.suricata.categorias[categoria],
                Via.generica,
                f"suricata.categorias:{categoria}",
            )
        return Classificacao(
            Categoria.desconhecido, Via.sem_mapeamento, f"suricata.assinaturas:{assinatura}"
        )


# --- conversão ---------------------------------------------------------------------------

_FUSO_SEM_DOIS_PONTOS = re.compile(r"([+-]\d{2})(\d{2})$")


def horario_do_alerta(alerta: Mapping[str, Any]) -> datetime:
    """Horário do alerta: `@timestamp` (indexador, AIT-ADS) ou `timestamp` (alerts.json)."""
    alerta = desembrulhar(alerta)
    return _horario(alerta.get("@timestamp") or alerta.get("timestamp"))


def _horario(valor: Any) -> datetime:
    if not isinstance(valor, str):
        raise AlertaInvalido("alerta sem @timestamp nem timestamp")
    texto = _FUSO_SEM_DOIS_PONTOS.sub(r"\1:\2", valor.replace("Z", "+00:00"))
    try:
        horario = datetime.fromisoformat(texto)
    except ValueError:
        raise AlertaInvalido(f"horário inválido: {valor!r}") from None
    if horario.tzinfo is None:
        raise AlertaInvalido(f"horário sem fuso: {valor!r}")
    return horario


def _ip(valor: Any) -> IPv4Address | IPv6Address | None:
    """IP do alerta, sem a porta que o fast.log acrescenta ("1.2.3.4:80"). Inválido vira None."""
    if not isinstance(valor, str) or not valor:
        return None
    texto = valor.strip()
    if texto.count(":") == 1:  # IPv4 com porta
        texto = texto.split(":")[0]
    elif texto.startswith("[") and "]" in texto:  # [IPv6]:porta
        texto = texto[1 : texto.index("]")]
    try:
        return ip_address(texto)
    except ValueError:
        return None


def _inteiro(valor: Any) -> int | str | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
        return int(valor)
    return valor if isinstance(valor, str) else None


def desembrulhar(alerta: Mapping[str, Any]) -> Mapping[str, Any]:
    """Tira o envelope do indexador (`_source`), se houver."""
    fonte = alerta.get("_source")
    return fonte if isinstance(fonte, Mapping) and "rule" in fonte else alerta


class AdaptadorWazuh:
    origem = "wazuh"

    def __init__(self, mapeamento: Mapeamento | None = None, descartar_fastlog: bool = True):
        """`descartar_fastlog`: as regras 201xx do fast.log repetem o que o Suricata já grava no
        eve.json. Desligue só se o Suricata (ou o Snort) chegar ao Wazuh apenas pelo fast.log."""
        self.mapeamento = mapeamento or Mapeamento.carregar()
        self.descartar_fastlog = descartar_fastlog
        self._descartadas = frozenset(self.mapeamento.descartar.regras_fastlog)

    def converter(self, alerta: Mapping[str, Any], tenant_id: str) -> list[Evento]:
        """Um evento por alerta; lista vazia para as cópias do fast.log."""
        return [evento] if (evento := self.converter_um(alerta, tenant_id)) else []

    def converter_um(self, alerta: Mapping[str, Any], tenant_id: str) -> Evento | None:
        alerta = desembrulhar(alerta)
        regra = alerta.get("rule")
        if not isinstance(regra, Mapping) or "id" not in regra:
            raise AlertaInvalido("alerta sem rule.id")
        regra_id = str(regra["id"])
        horario = _horario(alerta.get("@timestamp") or alerta.get("timestamp"))
        dados = alerta.get("data") if isinstance(alerta.get("data"), Mapping) else {}
        suricata = dados.get("alert") if isinstance(dados.get("alert"), Mapping) else None
        if suricata is not None and not suricata.get("signature"):
            suricata = None

        if suricata is None and self.descartar_fastlog and regra_id in self._descartadas:
            return None

        grupos = [str(g) for g in regra.get("groups") or []]
        agente = alerta.get("agent") if isinstance(alerta.get("agent"), Mapping) else {}
        predecoder = (
            alerta.get("predecoder") if isinstance(alerta.get("predecoder"), Mapping) else {}
        )
        evidencias: dict[str, Any] = {
            "regra": {
                "id": regra_id,
                "descricao": regra.get("description"),
                "nivel": regra.get("level"),
                "grupos": grupos,
            },
            "agente": {k: agente.get(k) for k in ("id", "name", "ip") if agente.get(k)},
        }
        mitre = regra.get("mitre")
        if isinstance(mitre, Mapping) and mitre.get("id"):
            evidencias["regra"]["mitre"] = list(mitre["id"])
        if alerta.get("location"):
            evidencias["local"] = alerta["location"]

        if suricata is not None:
            origem = "suricata"
            classificacao = self.mapeamento.classificar_suricata(
                str(suricata["signature"]), suricata.get("category")
            )
            severidade = _inteiro(suricata.get("severity"))
            ip_origem, ip_destino = _ip(dados.get("src_ip")), _ip(dados.get("dest_ip"))
            # O ativo do Suricata sai dos IPs (resolvidos pelo inventário da política).
            ativo = None
            evidencias["suricata"] = {
                "assinatura": suricata.get("signature"),
                "assinatura_id": _inteiro(suricata.get("signature_id")),
                "categoria": suricata.get("category"),
                "severidade": severidade,
                "acao": suricata.get("action"),
                "protocolo": dados.get("proto"),
                "porta_destino": _inteiro(dados.get("dest_port")),
            }
        else:
            origem = "wazuh"
            classificacao = self.mapeamento.classificar_wazuh(regra_id, grupos)
            severidade = _inteiro(regra.get("level"))
            # O ativo do Wazuh é a máquina que gerou o log: sem `dstip`, o destino é o agente.
            # Sem isso o inventário só achava o ativo pelo nome, e o AIT-ADS chama todos os
            # agentes de "wazuh-client" (o `predecoder.hostname` falta em 60% dos alertas).
            ip_origem = _ip(dados.get("srcip"))
            ip_destino = _ip(dados.get("dstip")) or _ip(agente.get("ip"))
            ativo = predecoder.get("hostname") or agente.get("name")

        evidencias["mapeamento"] = {"via": classificacao.via.value, "chave": classificacao.chave}
        id_origem = str(alerta["id"]) if alerta.get("id") else None
        try:
            return Evento(
                id=self._id(tenant_id, origem, id_origem, alerta),
                tenant_id=tenant_id,
                origem=origem,
                id_origem=id_origem,
                categoria=classificacao.categoria,
                severidade_origem=severidade,
                ip_origem=ip_origem,
                ip_destino=ip_destino,
                ativo=ativo,
                ocorrido_em=horario,
                evidencias=evidencias,
                bruto=dict(alerta),
            )
        except ValidationError as erro:
            raise AlertaInvalido(f"alerta {id_origem or '?'} não virou evento: {erro}") from erro

    @staticmethod
    def _id(tenant_id: str, origem: str, id_origem: str | None, alerta: Mapping[str, Any]) -> UUID:
        """Determinístico: pelo id do alerta na ferramenta ou, sem ele, pelo conteúdo. Assim a
        reentrega da mesma mensagem pela fila nunca vira um segundo evento."""
        if id_origem is None:
            conteudo = json.dumps(alerta, sort_keys=True, ensure_ascii=False, default=str)
            id_origem = "sha256:" + hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
        return uuid5(NAMESPACE_RONDA, f"{tenant_id}|{origem}|{id_origem}")


def iterar_jsonl(caminho: Path) -> Iterator[dict[str, Any]]:
    """Alertas de um arquivo JSON Lines (AIT-ADS, alerts.json), lidos linha a linha."""
    with caminho.open(encoding="utf-8") as arquivo:
        for numero, linha in enumerate(arquivo, start=1):
            if not linha.strip():
                continue
            try:
                yield json.loads(linha)
            except json.JSONDecodeError as erro:
                raise AlertaInvalido(f"{caminho.name}:{numero}: JSON inválido ({erro})") from None
