import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from tests.api.test_payments import API_KEY
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.db.models.payment import Payment

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client
        
        
@pytest.mark.asyncio
async def test_idempotency_race_condition(client):
    idempotency_key = str(uuid4())

    payload = {
        "amount": "100.00",
        "currency": "RUB",
        "description": "Race condition test",
        "metadata": {
            "order_id": "race-001",
        },
        "webhook_url": "https://example.com/webhook",
    }

    headers = {
        "X-API-Key": API_KEY,
        "Idempotency-Key": idempotency_key,
    }

    async def create_payment():
        return await client.post(
            "/api/v1/payments",
            headers=headers,
            json=payload,
        )

    responses = await asyncio.gather(
        *[create_payment() for _ in range(20)]
    )

    # Все запросы должны успешно завершиться
    assert all(
        response.status_code == 202
        for response in responses
    )

    # Все должны вернуть один и тот же payment_id
    payment_ids = {
        response.json()["payment_id"]
        for response in responses
    }

    assert len(payment_ids) == 1

    payment_id = next(iter(payment_ids))

    # Дополнительная проверка через БД
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Payment).where(
                Payment.idempotency_key == idempotency_key
            )
        )

        payments = result.scalars().all()

        assert len(payments) == 1
        assert str(payments[0].id) == payment_id
    
    
@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_with_different_payload(
    client,
):
    idempotency_key = str(uuid4())

    headers = {
        "X-API-Key": API_KEY,
        "Idempotency-Key": idempotency_key,
    }

    first_payload = {
        "amount": "100.00",
        "currency": "RUB",
        "description": "First payment",
        "metadata": {
            "order_id": "100",
        },
        "webhook_url": "https://example.com/webhook",
    }

    second_payload = {
        "amount": "500.00",
        "currency": "RUB",
        "description": "Different payment",
        "metadata": {
            "order_id": "500",
        },
        "webhook_url": "https://example.com/webhook",
    }

    first = await client.post(
        "/api/v1/payments",
        headers=headers,
        json=first_payload,
    )

    second = await client.post(
        "/api/v1/payments",
        headers=headers,
        json=second_payload,
    )

    assert first.status_code == 202

    assert second.status_code in {400, 409}