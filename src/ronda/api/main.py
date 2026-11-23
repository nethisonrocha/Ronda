from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ronda import __version__
from ronda.api.routes import eventos, incidentes, ingestao, metricas, politicas
from ronda.config import obter_configuracao

app = FastAPI(
    title="Ronda",
    version=__version__,
    description="Governança ITIL para alertas de segurança.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=obter_configuracao().cors_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas da fase 1 mantidas sem prefixo para retrocompatibilidade e expostas também em /v1.
app.include_router(eventos.router)
app.include_router(politicas.router)
app.include_router(eventos.router, prefix="/v1")
app.include_router(politicas.router, prefix="/v1")
app.include_router(ingestao.router)
app.include_router(incidentes.router)
app.include_router(metricas.router)


@app.get("/saude", tags=["operação"])
def saude() -> dict[str, str]:
    return {"status": "ok", "versao": __version__}
