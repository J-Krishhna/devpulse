from fastapi import FastAPI
from app.api.routes_query import router as query_router
from app.api.routes_webhook import router as webhook_router

app = FastAPI(title="DevPulse")

app.include_router(query_router)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    return {"status": "ok"}