from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from app.db.models.outbox import Outbox
from app.db.models.payment import Payment
from app.db.session import AsyncSessionLocal
from app.main import app
from tests.api.test_payments import API_KEY

from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_payment_and_outbox_are_created_atomically():
    idempotency_key = str(uuid4())

    class OutboxInsertError(Exception):
        pass

    payment_id = None

    def fail_outbox_insert(mapper, connection, target):
        nonlocal payment_id

        # Outbox.aggregate_id = Payment.id
        payment_id = target.aggregate_id

        raise OutboxInsertError("Outbox insert failed")

    event.listen(
        Outbox,
        "before_insert",
        fail_outbox_insert,
    )

    try:
        transport = ASGITransport(
            app=app,
            raise_app_exceptions=False,
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/payments",
                headers={
                    "X-API-Key": API_KEY,
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "amount": "100.00",
                    "currency": "RUB",
                    "description": "Atomic transaction test",
                    "metadata": {
                        "order_id": "atomic-001",
                    },
                    "webhook_url": "https://example.com/webhook",
                },
            )

        assert response.status_code == 500

    finally:
        event.remove(
            Outbox,
            "before_insert",
            fail_outbox_insert,
        )

    assert payment_id is not None

    async with AsyncSessionLocal() as session:
        # Payment должен отсутствовать
        payment = await session.scalar(
            select(Payment).where(
                Payment.id == payment_id
            )
        )

        assert payment is None

        # Outbox тоже должен отсутствовать
        outbox = await session.scalar(
            select(Outbox).where(
                Outbox.aggregate_id == payment_id
            )
        )

        assert outbox is None
        

@pytest.mark.asyncio
async def test_create_payment_creates_payment_and_outbox(client):
    idempotency_key = str(uuid4())

    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": idempotency_key,
        },
        json={
            "amount": "100.00",
            "currency": "RUB",
            "description": "Outbox atomicity test",
            "metadata": {
                "order_id": "atomic-001",
            },
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 202

    payment_id = response.json()["payment_id"]

    async with AsyncSessionLocal() as session:
        payment = await session.scalar(
            select(Payment).where(
                Payment.id == payment_id
            )
        )

        assert payment is not None

        outbox = await session.scalar(
            select(Outbox).where(
                Outbox.aggregate_id == payment.id
            )
        )

        assert outbox is not None
        assert outbox.published_at is None