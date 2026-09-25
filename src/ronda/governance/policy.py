"""Leitura e validação da política de um tenant (um arquivo YAML versionado)."""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from datetime import time as hora
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    IPvAnyNetwork,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from ronda.domain.event import TENANT_PATTERN
from ronda.domain.incident import TETO_RECORRENCIA, Contexto
from ronda.domain.priority import Criticidade, Impacto, Prioridade, Urgencia
from ronda.domain.taxonomy import Categoria


class PoliticaInvalida(ValueError):
    """A política não pôde ser lida ou não passou na validação."""


# --- duração ("15min", "1h", "2d") -------------------------------------------------

_DURACAO = re.compile(r"^\s*(\d+)\s*(min|h|d)\s*$")
_UNIDADES = {"min": "minutes", "h": "hours", "d": "days"}


def _ler_duracao(valor: Any) -> Any:
    if isinstance(valor, str):
        casamento = _DURACAO.match(valor)
        if not casamento:
            if valor.startswith("P"):  # ISO 8601, como a própria API devolve
                return valor
            raise ValueError(f"duração inválida {valor!r}; use por exemplo 15min, 1h ou 2d")
        quantidade, unidade = casamento.groups()
        return timedelta(**{_UNIDADES[unidade]: int(quantidade)})
    return valor


Duracao = Annotated[timedelta, BeforeValidator(_ler_duracao)]


# --- condições dos modificadores ("recorrencia_24h >= 5", "confirmado") ------------

_CONDICAO = re.compile(
    r"^\s*(?P<campo>[a-z_][a-z0-9_]*)\s*(?:(?P<op>>=|<=|==|!=|>|<)\s*(?P<valor>\S+))?\s*$"
)
_OPERADORES: dict[str, Callable[[Any, Any], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


class Condicao:
    """Comparação simples sobre um campo do Contexto; nada de eval."""

    def __init__(self, texto: str) -> None:
        casamento = _CONDICAO.match(texto)
        if not casamento:
            raise ValueError(f"condição inválida {texto!r}; use 'campo' ou 'campo >= 5'")
        campo, op, valor = casamento.group("campo", "op", "valor")
        campos = Contexto.model_fields
        if campo not in campos:
            raise ValueError(f"campo desconhecido {campo!r}; disponíveis: {', '.join(campos)}")
        booleano = campos[campo].annotation is bool
        self.texto = texto.strip()
        self.campo = campo
        self.op = op
        self.valor: Any = None
        if op is not None:
            if booleano:
                if op not in ("==", "!="):
                    raise ValueError(f"{campo!r} é verdadeiro/falso; compare só com == ou !=")
                if valor not in ("true", "false"):
                    raise ValueError(f"{campo!r} só aceita true ou false")
                self.valor = valor == "true"
            else:
                try:
                    self.valor = int(valor)
                except ValueError:
                    raise ValueError(f"{campo!r} é numérico; {valor!r} não é inteiro") from None

    def avaliar(self, contexto: Contexto) -> bool:
        atual = getattr(contexto, self.campo)
        if self.op is None:
            return bool(atual)
        return _OPERADORES[self.op](atual, self.valor)


# --- modelo da política -------------------------------------------------------------


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Ativo(_Estrito):
    nome: str = Field(min_length=1)
    rede: IPvAnyNetwork | None = None
    criticidade: Criticidade


class Modificador(_Estrito):
    se: str
    subir: int = Field(default=0, ge=0)
    descer: int = Field(default=0, ge=0)

    _condicao: Condicao = PrivateAttr()

    @model_validator(mode="after")
    def _validar(self) -> Modificador:
        if (self.subir > 0) == (self.descer > 0):
            raise ValueError(f"modificador {self.se!r}: informe só um entre subir e descer")
        self._condicao = Condicao(self.se)
        return self

    @property
    def passos(self) -> int:
        return self.subir - self.descer

    def aplica(self, contexto: Contexto) -> bool:
        return self._condicao.avaliar(contexto)


class RegrasUrgencia(_Estrito):
    base: dict[Categoria, Urgencia] = Field(default_factory=dict)
    modificadores: list[Modificador] = Field(default_factory=list)


class RegrasCorrelacao(_Estrito):
    janela: Duracao = Field(
        default=timedelta(minutes=30),
        description="Eventos da mesma chave com até este intervalo entre si formam um incidente",
    )

    @field_validator("janela")
    @classmethod
    def _janela_razoavel(cls, janela: timedelta) -> timedelta:
        if not timedelta(minutes=1) <= janela <= timedelta(days=7):
            raise ValueError("correlacao.janela precisa ficar entre 1min e 7d")
        return janela


ModoDaPolitica = Literal["imediata", "agrupada", "resumo_diario", "nunca"]
MODOS_PADRAO: dict[Prioridade, ModoDaPolitica] = {
    Prioridade.P1: "imediata",
    Prioridade.P2: "agrupada",
    Prioridade.P3: "resumo_diario",
    Prioridade.P4: "nunca",
}


def _ler_hora(valor: Any) -> Any:
    if isinstance(valor, str) and re.fullmatch(r"\d{1,2}:\d{2}", valor.strip()):
        h, m = valor.strip().split(":")
        return hora(int(h), int(m))
    return valor


Hora = Annotated[hora, BeforeValidator(_ler_hora)]


class HorarioSilencio(_Estrito):
    inicio: Hora
    fim: Hora
    """Pode atravessar a meia-noite (22:00 → 07:00)."""


class RegrasNotificacao(_Estrito):
    """Política anti-fadiga do tenant. O P1 é o único que fura o horário de silêncio."""

    canal: Literal["telegram"] = "telegram"
    destino_env: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="Variável de ambiente com o destino (o chat id); o valor nunca vai para o YAML",
    )
    fuso: str = "America/Fortaleza"
    modos: dict[Prioridade, ModoDaPolitica] = Field(default_factory=lambda: dict(MODOS_PADRAO))
    agrupamento: Duracao = Field(default=timedelta(minutes=10), description="Janela do P2 agrupado")
    silencio_por_origem: Duracao = Field(
        default=timedelta(minutes=30),
        description="Depois de notificar uma origem (mesma origem, categoria e ativo), não repete "
        "no mesmo nível durante este tempo",
    )
    horario_silencio: HorarioSilencio | None = None
    resumo_diario: Hora = hora(8, 0)

    @field_validator("fuso")
    @classmethod
    def _fuso_existe(cls, fuso: str) -> str:
        try:
            ZoneInfo(fuso)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"fuso desconhecido: {fuso!r}") from None
        return fuso

    @field_validator("modos")
    @classmethod
    def _modos_completos(
        cls, modos: dict[Prioridade, ModoDaPolitica]
    ) -> dict[Prioridade, ModoDaPolitica]:
        completos = dict(MODOS_PADRAO) | modos
        if completos[Prioridade.P1] == "nunca":
            raise ValueError("notificacao.modos: P1 não pode ser 'nunca'")
        return completos

    @property
    def zona(self) -> ZoneInfo:
        return ZoneInfo(self.fuso)


class Politica(_Estrito):
    tenant: str = Field(pattern=TENANT_PATTERN)
    versao: int = Field(ge=1)
    criticidade_padrao: Criticidade = Field(
        default=Criticidade.media,
        description="Criticidade de um ativo que o inventário não reconhece",
    )
    ativos: list[Ativo] = Field(default_factory=list)
    impacto: dict[Categoria, dict[Criticidade, Impacto]] = Field(default_factory=dict)
    urgencia: RegrasUrgencia = Field(default_factory=RegrasUrgencia)
    matriz: dict[Impacto, dict[Urgencia, Prioridade]]
    resposta: dict[Prioridade, Duracao] = Field(default_factory=dict)
    correlacao: RegrasCorrelacao = Field(default_factory=RegrasCorrelacao)
    notificacao: RegrasNotificacao | None = None
    """Sem o bloco, o tenant não recebe notificação (o dashboard continua mostrando tudo)."""

    @field_validator("urgencia")
    @classmethod
    def _recorrencia_abaixo_do_teto(cls, urgencia: RegrasUrgencia) -> RegrasUrgencia:
        for modificador in urgencia.modificadores:
            condicao = modificador._condicao
            limiar = condicao.valor if condicao.campo == "recorrencia_24h" else None
            if isinstance(limiar, int) and limiar > TETO_RECORRENCIA:
                raise ValueError(
                    f"modificador {modificador.se!r}: a recorrência satura em "
                    f"{TETO_RECORRENCIA}; o limiar nunca seria atingido"
                )
        return urgencia

    @field_validator("ativos")
    @classmethod
    def _nomes_unicos(cls, ativos: list[Ativo]) -> list[Ativo]:
        vistos: set[str] = set()
        for ativo in ativos:
            if ativo.nome in vistos:
                raise ValueError(f"ativo {ativo.nome!r} declarado mais de uma vez")
            vistos.add(ativo.nome)
        return ativos

    @field_validator("impacto")
    @classmethod
    def _impacto_completo(
        cls, impacto: dict[Categoria, dict[Criticidade, Impacto]]
    ) -> dict[Categoria, dict[Criticidade, Impacto]]:
        for categoria, linha in impacto.items():
            faltando = [c.value for c in Criticidade if c not in linha]
            if faltando:
                raise ValueError(
                    f"impacto.{categoria.value}: falta criticidade {', '.join(faltando)}"
                )
        return impacto

    @field_validator("matriz")
    @classmethod
    def _matriz_completa(
        cls, matriz: dict[Impacto, dict[Urgencia, Prioridade]]
    ) -> dict[Impacto, dict[Urgencia, Prioridade]]:
        for impacto in Impacto:
            if impacto not in matriz:
                raise ValueError(f"matriz: falta a linha de impacto {impacto.value}")
            faltando = [u.value for u in Urgencia if u not in matriz[impacto]]
            if faltando:
                raise ValueError(f"matriz.{impacto.value}: falta urgência {', '.join(faltando)}")
        return matriz


def ler_politica(dados: Any, origem: str = "política") -> Politica:
    try:
        return Politica.model_validate(dados)
    except ValidationError as erro:
        raise PoliticaInvalida(f"{origem} inválida:\n{erro}") from erro


def carregar_politica(caminho: Path) -> Politica:
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as erro:
        raise PoliticaInvalida(f"não foi possível ler {caminho}: {erro}") from erro
    return ler_politica(dados, str(caminho))


class PoliticaNaoEncontrada(LookupError):
    pass


class RepositorioPoliticas:
    """Políticas em disco, uma por tenant (<tenant>.yaml), relidas quando o arquivo muda."""

    def __init__(self, diretorio: Path) -> None:
        self.diretorio = diretorio
        self._cache: dict[str, tuple[int, Politica]] = {}

    def tenants(self) -> list[str]:
        """Tenants com arquivo de política no diretório (nome do arquivo válido)."""
        return sorted(
            c.stem for c in self.diretorio.glob("*.yaml") if re.fullmatch(TENANT_PATTERN, c.stem)
        )

    def obter(self, tenant: str) -> Politica:
        if not re.match(TENANT_PATTERN, tenant):
            raise PoliticaNaoEncontrada(tenant)
        caminho = self.diretorio / f"{tenant}.yaml"
        try:
            modificado = caminho.stat().st_mtime_ns
        except FileNotFoundError:
            raise PoliticaNaoEncontrada(tenant) from None
        guardado = self._cache.get(tenant)
        if guardado and guardado[0] == modificado:
            return guardado[1]
        politica = carregar_politica(caminho)
        if politica.tenant != tenant:
            raise PoliticaInvalida(
                f"{caminho}: o arquivo declara tenant {politica.tenant!r}, esperado {tenant!r}"
            )
        self._cache[tenant] = (modificado, politica)
        return politica
