from datetime import UTC, datetime

from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.db.models.outbox import Outbox
from app.db.session import AsyncSessionLocal


async def publish_outbox(
    broker: RabbitBroker,
) -> None:

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )

        events = result.scalars().all()

        for event in events:
            await broker.publish(
                message={
                    "event_id": str(event.id),
                    **event.payload,
                },
                exchange="payments",
                routing_key="payments.new",
                persist=True,
            )

            event.published_at = datetime.now(UTC)

        await session.commit()
