from app.broker.config import (
    PAYMENTS_DLX,
    PAYMENTS_DLQ,
    PAYMENTS_EXCHANGE,
    PAYMENTS_QUEUE,
    WEBHOOK_RETRY_1,
    WEBHOOK_RETRY_2,
    WEBHOOK_RETRY_3,

)
from app.broker.connection import broker


async def declare_topology() -> None:
    """
    Создаёт все RabbitMQ exchanges, queues
    и bindings для payment/webhook pipeline.
    """

    # PAYMENTS

    payments_exchange = await broker.declare_exchange(
        PAYMENTS_EXCHANGE
    )

    payments_dlx = await broker.declare_exchange(
        PAYMENTS_DLX
    )

    payments_queue = await broker.declare_queue(
        PAYMENTS_QUEUE
    )

    webhook_retry_1 = await broker.declare_queue(
        WEBHOOK_RETRY_1
    )

    webhook_retry_2 = await broker.declare_queue(
        WEBHOOK_RETRY_2
    )

    webhook_retry_3 = await broker.declare_queue(
        WEBHOOK_RETRY_3
    )

    payments_dlq = await broker.declare_queue(
        PAYMENTS_DLQ
    )

    # payments.new -> payments exchange

    await payments_queue.bind(
        payments_exchange,
        routing_key="payments.new",
    )


    # webhook.retry.1 -> payments exchange
    #
    # Нужен для broker.publish(..., queue=WEBHOOK_RETRY_1)


    await webhook_retry_1.bind(
        payments_exchange,
        routing_key="webhook.retry.1",
    )


    # webhook.retry.2 -> payments exchange


    await webhook_retry_2.bind(
        payments_exchange,
        routing_key="webhook.retry.2",
    )


    # webhook.retry.3 -> payments exchange


    await webhook_retry_3.bind(
        payments_exchange,
        routing_key="webhook.retry.3",
    )


    # payments.dlq <- payments.dlx


    await payments_dlq.bind(
        payments_dlx,
        routing_key="payments.dlq",
    )


