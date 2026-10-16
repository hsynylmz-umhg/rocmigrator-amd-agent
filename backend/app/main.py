"""
backend/app/main.py — FastAPI Main Application.
"""

from fastapi import FastAPI
from backend.app.api.routes import router

app = FastAPI(
    title="ROCmigrator Control Plane API",
    version="1.0.0",
    description="AMD Developer Cloud CUDA to HIP migration orchestrator",
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rocmigrator-backend"}
