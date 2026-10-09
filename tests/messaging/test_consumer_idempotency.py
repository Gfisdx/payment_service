from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.broker.consumer import handle_payment
from app.db.models.payment import Payment, PaymentStatus
from app.schemas.events import PaymentCreatedEvent
from tests.messaging.test_consumer import make_logger, make_message


@pytest.mark.asyncio
async def test_duplicate_payment_event_does_not_process_payment_twice(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.PENDING,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
    )

    db_session.add(payment)
    await db_session.commit()

    event = PaymentCreatedEvent(
        payment_id=payment.id,
    )

    with (
        patch(
            "app.broker.consumer.process_payment",
            new_callable=AsyncMock,
        ) as process_mock,
        patch(
            "app.broker.consumer.send_payment_webhook",
            new_callable=AsyncMock,
        ) as webhook_mock,
        patch(
            "app.broker.consumer.AsyncSessionLocal",
        ) as session_factory,
    ):
        session_factory.return_value.__aenter__.return_value = db_session

        await handle_payment(
            event=event,
            message=make_message(),
            logger=make_logger(),
        )

        await handle_payment(
            event=event,
            message=make_message(),
            logger=make_logger(),
        )

    process_mock.assert_awaited_once()