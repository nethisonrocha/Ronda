from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ronda.replay import ReplayInterrompido, enviar_por_http, reproduzir

T0 = datetime(2022, 1, 21, 0, 0, tzinfo=UTC)


class Relogio:
    """Relógio falso: dormir avança o tempo, e cada envio consome `custo` segundos."""

    def __init__(self, custo: float = 0.0):
        self.agora = 0.0
        self.custo = custo
        self.envios: list[tuple[float, list]] = []

    def __call__(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.agora += segundos

    def enviar(self, lote):
        self.envios.append((self.agora, [a["n"] for a in lote]))
        self.agora += self.custo


def alertas(*segundos):
    return [(T0 + timedelta(seconds=s), {"n": i}) for i, s in enumerate(segundos)]


def test_respeita_os_intervalos_divididos_pela_velocidade():
    relogio = Relogio()
    resultado = reproduzir(
        alertas(0, 60, 120), relogio.enviar, 60, relogio=relogio, dormir=relogio.dormir
    )
    assert relogio.envios == [(0.0, [0]), (1.0, [1]), (2.0, [2])]  # 1 min vira 1 s
    assert resultado.alertas == 3 and resultado.requisicoes == 3


def test_alertas_no_mesmo_instante_vao_na_mesma_requisicao():
    relogio = Relogio()
    reproduzir(alertas(0, 0, 0, 10), relogio.enviar, 1, relogio=relogio, dormir=relogio.dormir)
    assert relogio.envios == [(0.0, [0, 1, 2]), (10.0, [3])]


def test_atrasado_junta_o_que_venceu_e_respeita_o_lote_maximo():
    relogio = Relogio(custo=5.0)  # cada envio demora 5 s
    reproduzir(
        alertas(0, 1, 2, 3, 4, 5),
        relogio.enviar,
        1,
        lote_max=2,
        relogio=relogio,
        dormir=relogio.dormir,
    )
    lotes = [n for _, n in relogio.envios]
    # nada se perde nem troca de ordem
    assert [x for lote in lotes for x in lote] == list(range(6))
    assert all(len(lote) <= 2 for lote in lotes)


def test_velocidade_zero_envia_sem_esperar():
    relogio = Relogio()
    resultado = reproduzir(
        alertas(0, 3600, 7200), relogio.enviar, 0, relogio=relogio, dormir=relogio.dormir
    )
    assert relogio.envios == [(0.0, [0, 1, 2])] and resultado.segundos == 0


def test_velocidade_negativa_e_recusada():
    with pytest.raises(ValueError):
        reproduzir([], lambda lote: None, -1)


def transporte(*respostas):
    fila = list(respostas)
    recebidas = []

    def responder(request: httpx.Request) -> httpx.Response:
        recebidas.append(request)
        codigo = fila.pop(0)
        return httpx.Response(codigo, json={"aceitos": 1})

    return httpx.MockTransport(responder), recebidas


def test_envio_manda_o_token_e_tenta_de_novo_em_503():
    mock, recebidas = transporte(503, 202)
    with httpx.Client(transport=mock) as cliente:
        enviar_por_http(
            cliente, "http://x/v1/ingestao/wazuh", "rnd_segredo", dormir=lambda s: None
        )([{"a": 1}])
    assert len(recebidas) == 2
    assert recebidas[0].headers["authorization"] == "Bearer rnd_segredo"


def test_token_recusado_interrompe_sem_insistir():
    mock, recebidas = transporte(401)
    with httpx.Client(transport=mock) as cliente, pytest.raises(ReplayInterrompido, match="401"):
        enviar_por_http(cliente, "http://x", "rnd_x", dormir=lambda s: None)([{"a": 1}])
    assert len(recebidas) == 1


def test_erro_de_cliente_nao_repete():
    mock, recebidas = transporte(422)
    with httpx.Client(transport=mock) as cliente, pytest.raises(ReplayInterrompido, match="422"):
        enviar_por_http(cliente, "http://x", "rnd_x", dormir=lambda s: None)([{"a": 1}])
    assert len(recebidas) == 1
