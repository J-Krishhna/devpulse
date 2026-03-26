from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from app.api.routes_query import router as query_router
from app.api.routes_webhook import router as webhook_router
from app.api.routes_ws import router as ws_router
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="DevPulse")

app.include_router(query_router)
app.include_router(webhook_router)
app.include_router(ws_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.ingestion.embedder import embed_chunks

@app.on_event("startup")
async def startup_event():
    # Warm up the model on startup so first query isn't slow
    embed_chunks(["warmup"])

from dotenv import load_dotenv
import os

load_dotenv()  # <-- THIS LINE IS REQUIRED

print("HF TOKEN:", os.getenv("HF_TOKEN")[:10])

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Civic Issues Reporting API", 
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {"status": "ok"}