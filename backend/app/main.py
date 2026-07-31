from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routers import circuit, events, health, recommendations

app = FastAPI(title="RaverCircuit API", version="0.1.0")

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"error": {"code": exc.status_code, "message": exc.detail}})

app.include_router(health.router)
app.include_router(events.router)
app.include_router(circuit.router)
app.include_router(recommendations.router)