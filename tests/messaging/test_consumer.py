from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.broker.consumer import handle_payment
from app.db.models.payment import Currency, Payment, PaymentStatus
from app.schemas.events import PaymentCreatedEvent
from app.services.payment_processor import PaymentProcessingError
from app.services.webhook import WebhookError, send_payment_webhook


def make_event(payment_id):
    return PaymentCreatedEvent(
        payment_id=payment_id,
    )


def make_message(headers=None):
    message = MagicMock()
    message.headers = headers or {}
    return message


def make_logger():
    logger = MagicMock()
    return logger


@pytest.mark.asyncio
async def test_consumer_processes_pending_payment_and_sends_webhook(
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

    event = make_event(payment.id)

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

    process_mock.assert_awaited_once()
    webhook_mock.assert_awaited_once()

    await db_session.refresh(payment)

    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None
    assert payment.webhook_sent_at is not None


@pytest.mark.asyncio
async def test_consumer_marks_payment_failed_when_processing_fails(
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

    event = make_event(payment.id)

    with (
        patch(
            "app.broker.consumer.process_payment",
            new_callable=AsyncMock,
            side_effect=PaymentProcessingError("processor failed"),
        ),
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

    await db_session.refresh(payment)

    assert payment.status == PaymentStatus.FAILED
    assert payment.processed_at is not None
    assert payment.webhook_sent_at is not None

    webhook_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_does_not_process_already_processed_payment(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
    )

    db_session.add(payment)
    await db_session.commit()

    event = make_event(payment.id)

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

    process_mock.assert_not_awaited()
    webhook_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_does_not_send_webhook_twice(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
        webhook_sent_at=datetime.now(UTC),
    )

    db_session.add(payment)
    await db_session.commit()

    event = make_event(payment.id)

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

    process_mock.assert_not_awaited()
    webhook_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_failure_publishes_retry_1(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
    )

    db_session.add(payment)
    await db_session.commit()

    event = make_event(payment.id)

    with (
        patch(
            "app.broker.consumer.send_payment_webhook",
            new_callable=AsyncMock,
            side_effect=WebhookError("webhook failed"),
        ),
        patch(
            "app.broker.consumer.publish_webhook_retry",
            new_callable=AsyncMock,
        ) as retry_mock,
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

    retry_mock.assert_awaited_once_with(
        event=event,
        attempt=1,
    )

    await db_session.refresh(payment)

    assert payment.webhook_sent_at is None


@pytest.mark.asyncio
async def test_webhook_retry_1_publishes_retry_2(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
    )

    db_session.add(payment)
    await db_session.commit()

    event = make_event(payment.id)

    with (
        patch(
            "app.broker.consumer.send_payment_webhook",
            new_callable=AsyncMock,
            side_effect=WebhookError("webhook failed"),
        ),
        patch(
            "app.broker.consumer.publish_webhook_retry",
            new_callable=AsyncMock,
        ) as retry_mock,
        patch(
            "app.broker.consumer.AsyncSessionLocal",
        ) as session_factory,
    ):
        session_factory.return_value.__aenter__.return_value = db_session

        await handle_payment(
            event=event,
            message=make_message(
                {"x-payment-retry-attempt": 1},
            ),
            logger=make_logger(),
        )

    retry_mock.assert_awaited_once_with(
        event=event,
        attempt=2,
    )

    await db_session.refresh(payment)
    assert payment.webhook_sent_at is None


@pytest.mark.asyncio
async def test_webhook_retry_2_publishes_retry_3(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
    )

    db_session.add(payment)
    await db_session.commit()

    event = make_event(payment.id)

    with (
        patch(
            "app.broker.consumer.send_payment_webhook",
            new_callable=AsyncMock,
            side_effect=WebhookError("webhook failed"),
        ),
        patch(
            "app.broker.consumer.publish_webhook_retry",
            new_callable=AsyncMock,
        ) as retry_mock,
        patch(
            "app.broker.consumer.AsyncSessionLocal",
        ) as session_factory,
    ):
        session_factory.return_value.__aenter__.return_value = db_session

        await handle_payment(
            event=event,
            message=make_message(
                {"x-payment-retry-attempt": 2},
            ),
            logger=make_logger(),
        )

    retry_mock.assert_awaited_once_with(
        event=event,
        attempt=3,
    )

    await db_session.refresh(payment)
    assert payment.webhook_sent_at is None
    
@pytest.mark.asyncio
async def test_webhook_failure_never_sets_webhook_sent_at(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
    )

    db_session.add(payment)
    await db_session.commit()

    event = make_event(payment.id)

    with (
        patch(
            "app.broker.consumer.send_payment_webhook",
            new_callable=AsyncMock,
            side_effect=WebhookError("failed"),
        ),
        patch(
            "app.broker.consumer.publish_webhook_retry",
            new_callable=AsyncMock,
        ),
        patch(
            "app.broker.consumer.AsyncSessionLocal",
        ) as session_factory,
    ):
        session_factory.return_value.__aenter__.return_value = db_session

        await handle_payment(
            event=event,
            message=make_message(
                {"x-payment-retry-attempt": 3},
            ),
            logger=make_logger(),
        )

    await db_session.refresh(payment)

    assert payment.webhook_sent_at is None
    
    
@pytest.mark.asyncio
async def test_webhook_retry_succeeds_after_first_failure(
    db_session,
):
    payment = Payment(
        id=uuid4(),
        amount="100.00",
        currency="USD",
        description="Webhook retry test",
        metadata_={},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key=f"key-{uuid4()}",
        webhook_url="https://example.com/webhook",
        processed_at=datetime.now(UTC),
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
            side_effect=[
                WebhookError("temporary webhook failure"),
                None,
            ],
        ) as webhook_mock,
        patch(
            "app.broker.consumer.publish_webhook_retry",
            new_callable=AsyncMock,
        ) as retry_mock,
        patch(
            "app.broker.consumer.AsyncSessionLocal",
        ) as session_factory,
    ):
        session_factory.return_value.__aenter__.return_value = db_session

        # Первая попытка
        await handle_payment(
            event=event,
            message=make_message(),
            logger=make_logger(),
        )

        # Retry после первой ошибки
        await handle_payment(
            event=event,
            message=make_message(
                {
                    "x-payment-retry-attempt": 1,
                }
            ),
            logger=make_logger(),
        )

    # Платёж уже был обработан.
    # При webhook retry процессинг платежа повторяться не должен.
    process_mock.assert_not_awaited()

    # Было две попытки отправить webhook.
    assert webhook_mock.await_count == 2

    # Только первая попытка создала retry.
    retry_mock.assert_awaited_once_with(
        event=event,
        attempt=1,
    )

    await db_session.refresh(payment)

    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None
    assert payment.webhook_sent_at is not None
    


@pytest.mark.asyncio
async def test_webhook_payload_contains_correct_payment_data():
    payment_id = uuid4()

    payment = Payment(
        id=payment_id,
        amount=Decimal("1000.00"),
        currency=Currency.RUB,
        description="Test payment",
        metadata_={"order_id": "order-123"},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key="test-webhook-payload",
        webhook_url="http://test-webhook.local/webhook",
    )

    expected_payload = {
        "payment_id": str(payment_id),
        "status": "succeeded",
        "amount": "1000.00",
        "currency": "RUB",
    }

    response_mock = MagicMock()
    response_mock.raise_for_status = MagicMock()

    with patch(
        "app.services.webhook.httpx.AsyncClient"
    ) as client_mock:
        http_client = client_mock.return_value.__aenter__.return_value
        http_client.post = AsyncMock(return_value=response_mock)

        await send_payment_webhook(payment)

        http_client.post.assert_awaited_once_with(
            payment.webhook_url,
            json=expected_payload,
        )

    response_mock.raise_for_status.assert_called_once_with()
    
    
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("processing_fails", "expected_status"),
    [
        (False, PaymentStatus.SUCCEEDED),
        (True, PaymentStatus.FAILED),
    ],
)
async def test_process_payment_success_and_failure(
    db_session,
    processing_fails,
    expected_status,
):
    payment = Payment(
        id=uuid4(),
        amount=Decimal("1000.00"),
        currency=Currency.RUB,
        description="Test payment",
        metadata_={},
        status=PaymentStatus.PENDING,
        idempotency_key=f"test-process-{uuid4()}",
        webhook_url="http://test-webhook.local/webhook",
    )
    db_session.add(payment)
    await db_session.commit()

    event = PaymentCreatedEvent(payment_id=payment.id)
    message = MagicMock()
    message.headers = {}
    logger = MagicMock()

    if processing_fails:
        process_mock = AsyncMock(
            side_effect=PaymentProcessingError("Payment processing failed")
        )
    else:
        process_mock = AsyncMock()

    with (
        patch(
            "app.broker.consumer.AsyncSessionLocal"
        ) as session_factory,
        patch(
            "app.broker.consumer.process_payment",
            new=process_mock,
        ),
        patch(
            "app.broker.consumer.send_payment_webhook",
            new_callable=AsyncMock,
        ) as webhook_mock,
    ):
        session_factory.return_value.__aenter__.return_value = db_session

        await handle_payment(event, message, logger)

    await db_session.refresh(payment)

    assert payment.status == expected_status
    assert payment.processed_at is not None
    assert payment.webhook_sent_at is not None

    process_mock.assert_awaited_once()
    webhook_mock.assert_awaited_once_with(payment)