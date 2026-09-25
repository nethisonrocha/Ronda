import json
from uuid import uuid4

import httpx
import pytest

from ronda.notifier.channels.base import CanalFalso, ErroCanal, Mensagem
from ronda.notifier.channels.telegram import CanalTelegram, dados_do_botao, ler_botao

TOKEN = "123456:SEGREDO-do-bot"


def canal_com(responder):
    recebidas = []

    def tratar(request: httpx.Request) -> httpx.Response:
        recebidas.append(request)
        return responder(request)

    cliente = httpx.Client(transport=httpx.MockTransport(tratar))
    return CanalTelegram(TOKEN, cliente=cliente), recebidas


def test_envio_em_texto_puro_com_botao_de_reconhecer():
    canal, recebidas = canal_com(
        lambda r: httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})
    )
    notificacao_id = uuid4()
    id_externo = canal.enviar(
        Mensagem("999", "texto_com_*asterisco*", dados_do_botao(notificacao_id))
    )

    assert id_externo == "42"
    corpo = json.loads(recebidas[0].content)
    assert recebidas[0].url.path == f"/bot{TOKEN}/sendMessage"
    assert "parse_mode" not in corpo  # Markdown quebraria com _ e * de nomes de arquivo
    assert corpo["chat_id"] == "999" and corpo["text"] == "texto_com_*asterisco*"
    [[botao]] = corpo["reply_markup"]["inline_keyboard"]
    assert botao["callback_data"] == "r:" + notificacao_id.hex
    assert len(botao["callback_data"].encode()) <= 64  # limite do Telegram


def test_mensagem_sem_botao_nao_leva_teclado():
    canal, recebidas = canal_com(
        lambda r: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    )
    canal.enviar(Mensagem("999", "resumo"))
    assert "reply_markup" not in json.loads(recebidas[0].content)


@pytest.mark.parametrize(
    "responder",
    [
        lambda r: httpx.Response(
            400, json={"ok": False, "description": f"Bad Request: chat not found ({TOKEN})"}
        ),
        lambda r: httpx.Response(502, text="gateway"),
        lambda r: (_ for _ in ()).throw(
            httpx.ConnectError(f"falhou em https://api.telegram.org/bot{TOKEN}/sendMessage")
        ),
    ],
)
def test_erro_do_telegram_nunca_carrega_o_token(responder):
    canal, _ = canal_com(responder)
    with pytest.raises(ErroCanal) as erro:
        canal.enviar(Mensagem("999", "x"))
    assert TOKEN not in str(erro.value) and "SEGREDO" not in str(erro.value)


def test_atualizacoes_e_resposta_ao_clique():
    def responder(request):
        metodo = request.url.path.rsplit("/", 1)[-1]
        if metodo == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})
        return httpx.Response(200, json={"ok": True, "result": True})

    canal, recebidas = canal_com(responder)
    assert canal.atualizacoes(5, espera=1) == [{"update_id": 7}]
    canal.responder_clique("abc", "Reconhecido")
    assert json.loads(recebidas[0].content)["offset"] == 5
    assert json.loads(recebidas[1].content) == {"callback_query_id": "abc", "text": "Reconhecido"}


def test_ler_botao():
    i = uuid4()
    assert ler_botao(dados_do_botao(i)) == i
    assert ler_botao("r:naoehex") is None
    assert ler_botao("x:" + i.hex) is None
    assert ler_botao(None) is None


def test_canal_falso_guarda_e_falha_quando_pedido():
    canal = CanalFalso(falhar=1)
    with pytest.raises(ErroCanal):
        canal.enviar(Mensagem("1", "a"))
    assert canal.enviar(Mensagem("1", "b")) == "falso-1"
    assert [m.texto for m in canal.enviadas] == ["b"]
