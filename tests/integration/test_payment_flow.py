import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.db.models.outbox import Outbox
from app.db.models.payment import Payment,PaymentStatus

from conftest import WEBHOOK_URL
from conftest import API_KEY


@pytest.mark.asyncio
async def test_full_payment_flow(client):
    idempotency_key = "integration-test-full-payment-flow"

    response = await client.post(
        "/api/v1/payments",
        headers={
            "Idempotency-Key": idempotency_key,
            "X-API-Key": API_KEY,
        },
        json={
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Integration test payment",
            "webhook_url": WEBHOOK_URL,
        },
    )

    assert response.status_code == 202, response.text

    payment_id = response.json()["payment_id"]

    # Проверяем, что платёж и событие Outbox созданы.
    async with AsyncSessionLocal() as session:
        payment = await session.get(Payment, payment_id)
        assert payment is not None

        outbox_result = await session.execute(
            select(Outbox).where(
                Outbox.aggregate_id == payment.id,
            )
        )
        outbox_events = outbox_result.scalars().all()

        assert outbox_events, "Для платежа не создано событие Outbox"

    # Ждём обработки реальным Consumer и отправки webhook.
    deadline = datetime.now(UTC) + timedelta(seconds=30)

    while datetime.now(UTC) < deadline:
        async with AsyncSessionLocal() as session:
            payment = await session.get(Payment, payment_id)

            assert payment is not None

            if (
                payment.status
                in (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED)
                and payment.processed_at is not None
                and payment.webhook_sent_at is not None
            ):
                break

        await asyncio.sleep(0.25)
    else:
        pytest.fail(
            "Платёж не завершился или webhook не был отправлен "
            "за отведённое время"
        )

    # Проверяем наблюдаемый результат обработки.
    assert payment.status in (
        PaymentStatus.SUCCEEDED,
        PaymentStatus.FAILED,
    )
    assert payment.processed_at is not None
    assert payment.webhook_sent_at is not None

    # Проверяем, что событие Outbox существует и опубликовано.
    async with AsyncSessionLocal() as session:
        outbox_result = await session.execute(
            select(Outbox).where(
                Outbox.aggregate_id == payment.id,
            )
        )
        outbox_events = outbox_result.scalars().all()

        assert outbox_events, "Событие Outbox отсутствует"
        assert any(
            event.published_at is not None
            for event in outbox_events
        ), "Событие Outbox не было опубликовано"