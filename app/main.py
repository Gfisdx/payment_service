from fastapi import FastAPI

from app.api.v1.payments import router as payments_router
from app.core.config import settings
from app.api.webhook_test import router as webhook_test_router

app = FastAPI(
    title=settings.app_name,
)


app.include_router(payments_router)
app.include_router(webhook_test_router)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
    }
