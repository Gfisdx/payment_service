from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox import Outbox
from app.db.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreateRequest

class IdempotencyConflictError(Exception):
    pass

class PaymentService:
    async def create_payment(
        self,
        session: AsyncSession,
        data: PaymentCreateRequest,
        idempotency_key: str,
    ) -> Payment:

        result = await session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )

        existing_payment = result.scalar_one_or_none()

        if existing_payment is not None:

            if not self._payload_matches(existing_payment, data):
                raise IdempotencyConflictError(
                    "Idempotency-Key cannot be reused with different payload"
                )
                
            return existing_payment

        payment = Payment(
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            metadata_=data.metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            webhook_url=str(data.webhook_url),
        )

        session.add(payment)

        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()

            result = await session.execute(
                select(Payment).where(
                    Payment.idempotency_key == idempotency_key
                )
            )

            existing_payment = result.scalar_one()

            if not self._payload_matches(existing_payment, data):
                raise IdempotencyConflictError(
                    "Idempotency-Key cannot be reused with different payload"
                )

            return existing_payment
        
        outbox = Outbox(
            event_type="payment.created",
            aggregate_id=payment.id,
            payload={
                "payment_id": str(payment.id),
            },
        )

        session.add(outbox)

        await session.commit()

        await session.refresh(payment)

        return payment
    
    
    def _payload_matches(self, payment: Payment,data: PaymentCreateRequest) -> bool:
        return (
            payment.amount == data.amount
            and payment.currency == data.currency
            and payment.description == data.description
            and payment.metadata_ == data.metadata
            and payment.webhook_url == str(data.webhook_url)
        )
    

    async def get_payment(
        self,
        session: AsyncSession,
        payment_id: UUID,
    ) -> Payment | None:

        result = await session.execute(select(Payment).where(Payment.id == payment_id))

        return result.scalar_one_or_none()
