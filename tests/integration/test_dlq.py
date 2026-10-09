import asyncio
import json
from uuid import uuid4

import aio_pika
import pytest

from conftest import RABBITMQ_URL

RETRY_3_QUEUE = "webhook.retry.3"
DLQ_QUEUE = "payments.dlq"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_retry_exhaustion_goes_to_dlq():
    payment_id = str(uuid4())
    event_id = str(uuid4())

    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    try:
        channel = await connection.channel()

        # Проверяем, что очереди существуют.
        retry_3_queue = await channel.declare_queue(
            RETRY_3_QUEUE,
            passive=True,
        )

        dlq_queue = await channel.declare_queue(
            DLQ_QUEUE,
            passive=True,
        )

        # Удаляем старые сообщения из DLQ.
        await dlq_queue.purge()

        payload = {
            "payment_id": payment_id,
            "event_id": event_id,
        }

        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        # Отправляем сообщение в retry #3.
        await channel.default_exchange.publish(
            message,
            routing_key=RETRY_3_QUEUE,
        )

        # Ждём:
        #
        # webhook.retry.3
        #       ↓
        #     TTL 4 sec
        #       ↓
        # payments.dlx
        #       ↓
        # payments.dlq
        dlq_message = None

        timeout = 10
        interval = 0.25
        attempts = int(timeout / interval)

        for _ in range(attempts):
            dlq_message = await dlq_queue.get(
                fail=False,
                no_ack=False,
            )

            if dlq_message is not None:
                break

            await asyncio.sleep(interval)

        assert dlq_message is not None, (
            "Message was not moved from "
            f"{RETRY_3_QUEUE} to {DLQ_QUEUE}"
        )

        async with dlq_message.process():
            received_payload = json.loads(
                dlq_message.body.decode()
            )

            assert received_payload["payment_id"] == payment_id
            assert received_payload["event_id"] == event_id

            assert dlq_message.content_type == "application/json"

    finally:
        await connection.close()