"""Motor de governança: evento + contexto + política → prioridade P1–P4 com rastro.

Determinístico e sem I/O; a mesma entrada sempre produz a mesma decisão.
"""

from __future__ import annotations

from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address

from pydantic import BaseModel

from ronda.domain.event import Evento
from ronda.domain.incident import Contexto
from ronda.domain.priority import Criticidade, Impacto, Prioridade, Urgencia
from ronda.domain.taxonomy import PRIORIDADE_BASE
from ronda.governance.policy import Ativo, Politica
from ronda.governance.trace import Rastro, formatar_duracao


class Decisao(BaseModel):
    prioridade: Prioridade
    impacto: Impacto | None
    urgencia: Urgencia | None
    ativo: str | None
    criticidade: Criticidade
    resposta: timedelta | None
    politica_versao: int
    prioridade_base: bool
    """Verdadeiro quando a política não tinha regra e valeu a prioridade base da taxonomia."""
    rastro: Rastro


class Motor:
    def __init__(self, politica: Politica) -> None:
        self.politica = politica
        self._por_nome = {ativo.nome: ativo for ativo in politica.ativos}
        # A rede mais específica vence quando duas se sobrepõem.
        self._por_rede = sorted(
            (a for a in politica.ativos if a.rede is not None),
            key=lambda a: a.rede.prefixlen,  # type: ignore[union-attr]
            reverse=True,
        )

    def avaliar(self, evento: Evento, contexto: Contexto | None = None) -> Decisao:
        politica = self.politica
        if evento.tenant_id != politica.tenant:
            raise ValueError(
                f"evento do tenant {evento.tenant_id!r} avaliado com a política "
                f"de {politica.tenant!r}"
            )
        contexto = contexto or Contexto()
        rastro = Rastro()
        categoria = evento.categoria
        rastro.registrar("categoria", categoria.value, origem=evento.origem)

        ativo, criticidade = self._resolver_ativo(evento, rastro)

        linha_impacto = politica.impacto.get(categoria)
        urgencia_base = politica.urgencia.base.get(categoria)
        impacto: Impacto | None = None
        urgencia: Urgencia | None = None

        if linha_impacto is None or urgencia_base is None:
            faltando = [
                nome
                for nome, regra in (("impacto", linha_impacto), ("urgência", urgencia_base))
                if regra is None
            ]
            prioridade = PRIORIDADE_BASE[categoria]
            rastro.registrar(
                "prioridade_base",
                f"sem regra de {' e '.join(faltando)} na política v{politica.versao}, "
                f"vale a prioridade base {prioridade.value}",
                faltando=faltando,
            )
        else:
            impacto = linha_impacto[criticidade]
            rastro.registrar("impacto", f"impacto {impacto.value}", criticidade=criticidade.value)
            urgencia = self._calcular_urgencia(urgencia_base, contexto, rastro)
            prioridade = politica.matriz[impacto][urgencia]

        resposta = politica.resposta.get(prioridade)
        prazo = f"resposta em {formatar_duracao(resposta)}" if resposta else "sem prazo de resposta"
        rastro.registrar("prioridade", f"{prioridade.value}, {prazo}", versao=politica.versao)

        return Decisao(
            prioridade=prioridade,
            impacto=impacto,
            urgencia=urgencia,
            ativo=ativo.nome if ativo else evento.ativo,
            criticidade=criticidade,
            resposta=resposta,
            politica_versao=politica.versao,
            prioridade_base=impacto is None,
            rastro=rastro,
        )

    def ativo_do_inventario(self, evento: Evento) -> str | None:
        """Nome do ativo do inventário que o evento atinge, ou None (usado na correlação)."""
        ativo, _ = self._encontrar_ativo(evento)
        return ativo.nome if ativo else None

    def _encontrar_ativo(self, evento: Evento) -> tuple[Ativo | None, str]:
        """Ordem: nome informado pela fonte, depois IP de destino, depois IP de origem."""
        if evento.ativo and evento.ativo in self._por_nome:
            return self._por_nome[evento.ativo], "nome"
        for campo, ip in (("ip_destino", evento.ip_destino), ("ip_origem", evento.ip_origem)):
            ativo = self._ativo_por_ip(ip)
            if ativo:
                return ativo, campo
        return None, ""

    def _resolver_ativo(self, evento: Evento, rastro: Rastro) -> tuple[Ativo | None, Criticidade]:
        ativo, via = self._encontrar_ativo(evento)
        if ativo:
            rastro.registrar(
                "ativo",
                f"ativo {ativo.nome} (criticidade {ativo.criticidade.value})",
                via=via,
            )
            return ativo, ativo.criticidade

        padrao = self.politica.criticidade_padrao
        descricao = (
            f"ativo {evento.ativo} fora do inventário" if evento.ativo else "ativo não identificado"
        )
        rastro.registrar("ativo", f"{descricao} (criticidade padrão {padrao.value})", via=None)
        return None, padrao

    def _ativo_por_ip(self, ip: IPv4Address | IPv6Address | None) -> Ativo | None:
        if ip is None:
            return None
        for ativo in self._por_rede:
            rede = ativo.rede
            if rede is not None and rede.version == ip.version and ip in rede:
                return ativo
        return None

    def _calcular_urgencia(self, base: Urgencia, contexto: Contexto, rastro: Rastro) -> Urgencia:
        urgencia = base
        rastro.registrar("urgencia", f"urgência {urgencia.value}")
        for modificador in self.politica.urgencia.modificadores:
            if not modificador.aplica(contexto):
                continue
            nova = urgencia.deslocar(modificador.passos)
            if nova == urgencia:
                rastro.registrar(
                    "modificador",
                    f"{modificador.se}: urgência já em {urgencia.value}, sem efeito",
                    condicao=modificador.se,
                )
                continue
            verbo = "sobe" if modificador.passos > 0 else "desce"
            rastro.registrar(
                "modificador",
                f"{modificador.se}: urgência {verbo} para {nova.value}",
                condicao=modificador.se,
                de=urgencia.value,
                para=nova.value,
            )
            urgencia = nova
        return urgencia
