from datetime import UTC, datetime

from faststream import Logger
from faststream.rabbit import RabbitMessage
from sqlalchemy import select

from app.broker.config import (
    PAYMENTS_EXCHANGE,
    PAYMENTS_QUEUE,
    WEBHOOK_RETRY_1,
    WEBHOOK_RETRY_2,
    WEBHOOK_RETRY_3,
)
from app.broker.connection import broker
from app.db.models.payment import Payment, PaymentStatus
from app.db.session import AsyncSessionLocal
from app.schemas.events import PaymentCreatedEvent
from app.services.payment_processor import (PaymentProcessingError, process_payment,)
from app.services.webhook import (WebhookError, send_payment_webhook,)

WEBHOOK_RETRIES = 3


async def publish_webhook_retry(event: PaymentCreatedEvent, attempt: int) -> None:
    retry_queues = {
        1: WEBHOOK_RETRY_1,
        2: WEBHOOK_RETRY_2,
        3: WEBHOOK_RETRY_3,
    }

    queue = retry_queues.get(attempt)
    
    if queue is None:
        raise ValueError(f"Invalid webhook retry attempt: {attempt}")

    headers = {"x-payment-retry-attempt": attempt}


    await broker.publish(
        message=event.model_dump(mode="json"),
        exchange=PAYMENTS_EXCHANGE,
        routing_key=queue.routing_key,
        persist=True,
        headers=headers,
    )


@broker.subscriber(PAYMENTS_QUEUE, PAYMENTS_EXCHANGE)
async def handle_payment(event: PaymentCreatedEvent, message: RabbitMessage, logger: Logger) -> None:
    headers = message.headers or {}

    webhook_attempt = int(headers.get("x-payment-retry-attempt", 0))


    logger.info(
        "Received payment=%s webhook_attempt=%s",
        event.payment_id,
        webhook_attempt,
    )

    try: 
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Payment).where(Payment.id == event.payment_id)
            )
            payment = result.scalar_one_or_none()

            if payment is None:
                raise RuntimeError(f"Payment {event.payment_id} not found")


            if payment.status == PaymentStatus.PENDING:
                
                logger.info("Processing payment=%s",payment.id)
                
                try:
                    await process_payment()
                except PaymentProcessingError as exc:
                    
                    logger.warning(
                        "Payment processing failed "
                        "payment=%s error=%s",
                        payment.id,
                        exc,
                    )
                    
                    payment.status = PaymentStatus.FAILED
                    payment.processed_at = datetime.now(UTC)

                else:
                    payment.status = PaymentStatus.SUCCEEDED
                    payment.processed_at = datetime.now(UTC)

                    logger.info(
                        "Payment processing succeeded "
                        "payment=%s",
                        payment.id,
                    )
                
                await session.commit()
                
            else:
                logger.info(
                    "Payment already processed "
                    "payment=%s status=%s",
                    payment.id,
                    payment.status,
                )
                
            # WEBHOOK
            
            if payment.webhook_sent_at is not None:
                
                logger.info(
                    "Webhook already sent "
                    "payment=%s",
                    payment.id,
                )

                return
            
            try:

                logger.info(
                    "Sending webhook "
                    "payment=%s attempt=%s",
                    payment.id,
                    webhook_attempt + 1,
                )

                await send_payment_webhook(payment)
            except WebhookError as exc:

                logger.warning(
                    "Webhook failed "
                    "payment=%s attempt=%s error=%s",
                    payment.id,
                    webhook_attempt + 1,
                    exc,
                )

                next_attempt = webhook_attempt + 1
                
                if next_attempt <= WEBHOOK_RETRIES:
                    await publish_webhook_retry(
                        event=event,
                        attempt=next_attempt,
                    )

                    if next_attempt < WEBHOOK_RETRIES:
                        logger.warning(
                            "Webhook retry scheduled "
                            "payment=%s attempt=%s",
                            payment.id,
                            next_attempt,
                        )
                    else:
                        logger.error(
                            "Webhook delivery failed after %s attempts; "
                            "message scheduled for DLQ "
                            "payment=%s",
                            WEBHOOK_RETRIES,
                            payment.id,
                        )

                    return
            
                logger.error(
                    "Webhook delivery permanently failed payment=%s",
                    payment.id,
                )
                return
            
            payment.webhook_sent_at = datetime.now(UTC)

            await session.commit()

            logger.info(
                "Webhook successfully sent "
                "payment=%s status=%s",
                payment.id,
                payment.status,
            )

    except Exception as exc:
        logger.exception(
            "Unexpected error while handling payment=%s",
            event.payment_id
        )
        raise