from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.broker.publisher import publish_outbox
from app.db.models.outbox import Outbox
from app.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_publish_outbox_publishes_unpublished_event():
    """
    Outbox publisher должен отправить событие
    и установить published_at.
    """

    payment_id = uuid4()

    async with AsyncSessionLocal() as session:
        outbox = Outbox(
            event_type="payment.new",
            aggregate_id=payment_id,
            payload={
                "payment_id": str(payment_id),
                "amount": "1000.00",
                "currency": "RUB",
            },
        )

        session.add(outbox)
        await session.commit()
        await session.refresh(outbox)

        outbox_id = outbox.id

    broker = AsyncMock()

    await publish_outbox(broker)

    calls = broker.publish.await_args_list

    assert any(
        call.kwargs["message"]["event_id"] == str(outbox_id)
        for call in calls
    )

    call = broker.publish.await_args

    assert call.kwargs["exchange"] == "payments"
    assert call.kwargs["routing_key"] == "payments.new"
    assert call.kwargs["persist"] is True

    message = call.kwargs["message"]

    assert message["event_id"] == str(outbox_id)
    assert message["payment_id"] == str(payment_id)
    assert message["amount"] == "1000.00"
    assert message["currency"] == "RUB"

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )

        saved_event = result.scalar_one()

        assert saved_event.published_at is not None


@pytest.mark.asyncio
async def test_publish_outbox_ignores_published_events():
    """
    Уже опубликованное событие не должно публиковаться повторно.
    """

    payment_id = uuid4()

    async with AsyncSessionLocal() as session:
        outbox = Outbox(
            event_type="payment.new",
            aggregate_id=payment_id,
            payload={
                "payment_id": str(payment_id),
            },
            published_at=datetime.now(UTC),
        )

        session.add(outbox)
        await session.commit()

    broker = AsyncMock()

    await publish_outbox(broker)

    broker.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_outbox_publishes_multiple_events():
    """
    Publisher должен обработать несколько
    неопубликованных событий.
    """

    payment_id_1 = uuid4()
    payment_id_2 = uuid4()

    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                Outbox(
                    event_type="payment.new",
                    aggregate_id=payment_id_1,
                    payload={
                        "payment_id": str(payment_id_1),
                    },
                ),
                Outbox(
                    event_type="payment.new",
                    aggregate_id=payment_id_2,
                    payload={
                        "payment_id": str(payment_id_2),
                    },
                ),
            ]
        )

        await session.commit()

    broker = AsyncMock()

    await publish_outbox(broker)

    assert broker.publish.await_count == 2

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Outbox)
            .where(
                Outbox.aggregate_id.in_(
                    [payment_id_1, payment_id_2]
                )
            )
        )

        events = result.scalars().all()

        assert len(events) == 2

        for event in events:
            assert event.published_at is not None


@pytest.mark.asyncio
async def test_publish_outbox_does_not_mark_event_if_publish_fails():
    """
    Если RabbitMQ publish завершился ошибкой,
    published_at не должен быть установлен.
    """

    payment_id = uuid4()

    async with AsyncSessionLocal() as session:
        outbox = Outbox(
            event_type="payment.new",
            aggregate_id=payment_id,
            payload={
                "payment_id": str(payment_id),
            },
        )

        session.add(outbox)
        await session.commit()

        outbox_id = outbox.id

    broker = AsyncMock()
    broker.publish.side_effect = RuntimeError("RabbitMQ unavailable")

    with pytest.raises(RuntimeError, match="RabbitMQ unavailable"):
        await publish_outbox(broker)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )

        saved_event = result.scalar_one()

        assert saved_event.published_at is None


@pytest.mark.asyncio
async def test_publish_outbox_can_retry_unpublished_event():
    """
    Если первая публикация не удалась,
    следующий запуск publisher должен снова
    попытаться отправить событие.
    """

    payment_id = uuid4()

    async with AsyncSessionLocal() as session:
        outbox = Outbox(
            event_type="payment.new",
            aggregate_id=payment_id,
            payload={
                "payment_id": str(payment_id),
            },
        )

        session.add(outbox)
        await session.commit()

        outbox_id = outbox.id

    # Первая попытка — RabbitMQ недоступен.
    failed_broker = AsyncMock()
    failed_broker.publish.side_effect = RuntimeError(
        "RabbitMQ unavailable"
    )

    with pytest.raises(RuntimeError):
        await publish_outbox(failed_broker)

    # Проверяем, что наше событие осталось unpublished.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )

        event = result.scalar_one()

        assert event.published_at is None

    # Вторая попытка — RabbitMQ снова доступен.
    working_broker = AsyncMock()

    await publish_outbox(working_broker)

    # Проверяем, что наше конкретное событие
    # действительно было опубликовано.
    calls = working_broker.publish.await_args_list

    assert any(
        call.kwargs["message"]["event_id"] == str(outbox_id)
        for call in calls
    )

    # Проверяем, что наше событие теперь published.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )

        event = result.scalar_one()

        assert event.published_at is not None