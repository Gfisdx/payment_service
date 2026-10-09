from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.broker.consumer import publish_webhook_retry
from app.broker.config import (
    PAYMENTS_EXCHANGE,
    WEBHOOK_RETRY_1,
    WEBHOOK_RETRY_2,
    WEBHOOK_RETRY_3,
)
from app.schemas.events import PaymentCreatedEvent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempt", "retry_queue"),
    [
        (1, WEBHOOK_RETRY_1),
        (2, WEBHOOK_RETRY_2),
        (3, WEBHOOK_RETRY_3),
    ],
)
async def test_publish_webhook_retry(
    attempt,
    retry_queue,
):
    event = PaymentCreatedEvent(
        payment_id=uuid4(),
    )

    with patch("app.broker.consumer.broker.publish",new_callable=AsyncMock) as publish_mock:
        await publish_webhook_retry(
            event=event,
            attempt=attempt,
        )

    publish_mock.assert_awaited_once()

    kwargs = publish_mock.await_args.kwargs

    assert kwargs["exchange"] == PAYMENTS_EXCHANGE
    assert kwargs["routing_key"] == retry_queue.routing_key
    assert kwargs["persist"] is True
    assert kwargs["headers"] == {
        "x-payment-retry-attempt": attempt,
    }

    assert kwargs["message"] == event.model_dump(mode="json")


@pytest.mark.asyncio
async def test_publish_webhook_retry_rejects_invalid_attempt():
    event = PaymentCreatedEvent(
        payment_id=uuid4(),
    )

    with pytest.raises(ValueError, match="Invalid webhook retry attempt"):
        await publish_webhook_retry(
            event=event,
            attempt=4,
        )