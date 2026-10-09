from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(
    prefix="/test",
    tags=["Test Webhook"],
)


@router.post("/webhook")
async def test_webhook(body: Any = Body(...)):
    print("=" * 50)
    print("WEBHOOK RECEIVED")
    print(body)
    print("=" * 50)

    return {"received": True}