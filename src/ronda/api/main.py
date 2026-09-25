from fastapi import FastAPI

from ronda import __version__
from ronda.api.routes import eventos, ingestao, politicas

app = FastAPI(
    title="Ronda",
    version=__version__,
    description="Governança ITIL para alertas de segurança.",
)
app.include_router(eventos.router)
app.include_router(politicas.router)
app.include_router(ingestao.router)


@app.get("/saude", tags=["operação"])
def saude() -> dict[str, str]:
    return {"status": "ok", "versao": __version__}
