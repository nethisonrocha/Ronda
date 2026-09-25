"""Canal Telegram: envio com botão de reconhecimento, e leitura dos cliques por long polling.

Texto puro (sem `parse_mode`): nome de arquivo e código trazem `_`, `*` e `[]`, e o Telegram
recusa a mensagem inteira quando o Markdown não fecha. O token vai só na URL da chamada e nunca
aparece em erro nem em log.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from ronda.notifier.channels.base import ErroCanal, Mensagem

log = logging.getLogger(__name__)

PREFIXO_BOTAO = "r:"
TEXTO_BOTAO = "✅ Reconhecer"


def dados_do_botao(notificacao_id: UUID) -> str:
    """Cabe nos 64 bytes do callback do Telegram: "r:" + 32 hexadecimais."""
    return PREFIXO_BOTAO + notificacao_id.hex


def ler_botao(dados: str | None) -> UUID | None:
    if not dados or not dados.startswith(PREFIXO_BOTAO):
        return None
    try:
        return UUID(hex=dados[len(PREFIXO_BOTAO) :])
    except ValueError:
        return None


class CanalTelegram:
    def __init__(
        self,
        token: str,
        cliente: httpx.Client | None = None,
        base: str = "https://api.telegram.org",
        timeout: float = 15.0,
    ) -> None:
        self._token = token
        self._cliente = cliente or httpx.Client(timeout=timeout)
        self._base = base.rstrip("/")

    def _chamar(self, metodo: str, dados: dict[str, Any], timeout: float | None = None) -> Any:
        try:
            resposta = self._cliente.post(
                f"{self._base}/bot{self._token}/{metodo}", json=dados, timeout=timeout
            )
        except httpx.HTTPError as erro:
            # str(erro) pode trazer a URL, e a URL traz o token: só o tipo sai daqui.
            raise ErroCanal(f"telegram {metodo}: falha de rede ({type(erro).__name__})") from None
        try:
            corpo = resposta.json()
        except ValueError:
            raise ErroCanal(
                f"telegram {metodo}: resposta {resposta.status_code} sem JSON"
            ) from None
        if not corpo.get("ok"):
            descricao = str(corpo.get("description", "sem descrição")).replace(self._token, "***")
            raise ErroCanal(f"telegram {metodo}: {resposta.status_code} {descricao}")
        return corpo.get("result")

    def enviar(self, mensagem: Mensagem) -> str:
        dados: dict[str, Any] = {
            "chat_id": mensagem.destino,
            "text": mensagem.texto,
            "disable_web_page_preview": True,
        }
        if mensagem.botao:
            dados["reply_markup"] = {
                "inline_keyboard": [[{"text": TEXTO_BOTAO, "callback_data": mensagem.botao}]]
            }
        resultado = self._chamar("sendMessage", dados)
        return str(resultado["message_id"])

    def responder_clique(self, clique_id: str, texto: str) -> None:
        self._chamar("answerCallbackQuery", {"callback_query_id": clique_id, "text": texto[:200]})

    def atualizacoes(self, deslocamento: int | None, espera: int = 25) -> list[dict[str, Any]]:
        dados: dict[str, Any] = {"timeout": espera, "allowed_updates": ["callback_query"]}
        if deslocamento is not None:
            dados["offset"] = deslocamento
        return self._chamar("getUpdates", dados, timeout=espera + 10) or []
