"""Linha de comando `ronda`.

    ronda replay --cenario russellmitchell --velocidade 60
    ronda worker
    ronda token criar --tenant demo --nome wazuh-vps
    ronda token listar --tenant demo
    ronda token revogar --tenant demo --id <uuid>

O token do replay vem de RONDA_TOKEN (ou `--token`, que fica no histórico do shell).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import redis

from ronda.config import obter_configuracao
from ronda.replay import (
    ReplayInterrompido,
    alertas_do_cenario,
    caminho_do_cenario,
    enviar_por_http,
    reproduzir,
)


def _replay(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("RONDA_TOKEN")
    if not token:
        print("defina RONDA_TOKEN (ou --token) com um token de ingestão do tenant", file=sys.stderr)
        return 2
    caminho = caminho_do_cenario(Path(args.dados), args.cenario)
    url = args.url.rstrip("/") + "/v1/ingestao/wazuh"
    print(f"replay de {caminho.name} para {url} em {args.velocidade}x", file=sys.stderr)
    with httpx.Client() as cliente:
        try:
            resultado = reproduzir(
                alertas_do_cenario(caminho, pular=args.pular, limite=args.limite),
                enviar_por_http(cliente, url, token),
                args.velocidade,
                lote_max=args.lote,
            )
        except ReplayInterrompido as erro:
            print(f"replay interrompido: {erro}", file=sys.stderr)
            return 1
    print(
        f"{resultado.alertas} alertas em {resultado.requisicoes} requisições, "
        f"{resultado.segundos:.1f} s (maior atraso {resultado.atraso_max:.2f} s)"
    )
    return 0


def _worker(args: argparse.Namespace) -> int:
    from ronda.storage.database import BancoDeDados
    from ronda.workers.ingestao import WorkerIngestao
    from ronda.workers.processadores import GravarEventos

    configuracao = obter_configuracao()
    if configuracao.url_redis is None:
        print("defina RONDA_REDIS_URL", file=sys.stderr)
        return 2
    cliente = redis.Redis.from_url(str(configuracao.url_redis), decode_responses=True)
    banco = BancoDeDados.da_configuracao(configuracao)
    worker = WorkerIngestao(
        cliente, GravarEventos(banco), consumidor=args.consumidor, lote=args.lote
    )
    parar = threading.Event()
    try:
        worker.rodar(parar)
    except KeyboardInterrupt:
        parar.set()
    finally:
        banco.fechar()
    return 0


def _token(args: argparse.Namespace) -> int:
    from ronda.storage.database import BancoDeDados
    from ronda.storage.repositories import RepositorioTenants, RepositorioTokens

    configuracao = obter_configuracao()
    # Criar e revogar token é tarefa de administração: roda com a URL de migração (dono).
    url = configuracao.url_banco_migracao or configuracao.url_banco
    if url is None:
        print("defina RONDA_DATABASE_MIGRATION_URL", file=sys.stderr)
        return 2
    banco = BancoDeDados(str(url))
    try:
        with banco.sessao(args.tenant) as sessao:
            tokens = RepositorioTokens(sessao)
            if args.acao == "criar":
                RepositorioTenants(sessao).garantir(args.tenant)
                token, registro = tokens.criar(args.nome)
                print(f"token {registro.id} ({registro.nome}) do tenant {args.tenant}:")
                print(token)
                print("guarde agora: ele não é mostrado de novo", file=sys.stderr)
            elif args.acao == "listar":
                for t in tokens.listar():
                    estado = "revogado" if t.revogado_em else "ativo"
                    print(f"{t.id}  {t.nome:24} {estado:9} criado em {t.criado_em:%Y-%m-%d %H:%M}")
            else:
                ok = tokens.revogar(UUID(args.id), datetime.now(UTC))
                print("revogado" if ok else "não encontrado ou já revogado")
                return 0 if ok else 1
    finally:
        banco.fechar()
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ronda", description="Governança ITIL para alertas.")
    sub = parser.add_subparsers(dest="comando", required=True)

    replay = sub.add_parser("replay", help="reenvia um cenário do AIT-ADS ao endpoint de ingestão")
    replay.add_argument("--cenario", required=True, help="ex.: russellmitchell, fox")
    replay.add_argument("--velocidade", type=float, default=1.0, help="fator; 0 envia sem espera")
    replay.add_argument("--url", default="http://127.0.0.1:8000")
    replay.add_argument("--token", help="prefira a variável RONDA_TOKEN")
    replay.add_argument("--dados", default="data/raw/ait-ads/json")
    replay.add_argument("--pular", type=int, default=0, help="alertas a pular no início")
    replay.add_argument("--limite", type=int, help="quantos alertas enviar (um trecho)")
    replay.add_argument("--lote", type=int, default=500, help="máximo de alertas por requisição")
    replay.set_defaults(funcao=_replay)

    worker = sub.add_parser("worker", help="consome a fila de ingestão e grava os eventos")
    worker.add_argument("--consumidor", help="nome no grupo (padrão: host-pid)")
    worker.add_argument("--lote", type=int, default=100)
    worker.set_defaults(funcao=_worker)

    token = sub.add_parser("token", help="tokens de ingestão por tenant")
    token.add_argument("acao", choices=["criar", "listar", "revogar"])
    token.add_argument("--tenant", required=True)
    token.add_argument("--nome", default="padrao")
    token.add_argument("--id", help="id do token (para revogar)")
    token.set_defaults(funcao=_token)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = construir_parser().parse_args(argv)
    if args.comando == "token" and args.acao == "revogar" and not args.id:
        print("informe --id do token", file=sys.stderr)
        return 2
    return args.funcao(args)


if __name__ == "__main__":
    sys.exit(main())
