from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import IdempotencyKey, get_db
from app.core.security import verify_api_key
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentResponse,
)
from app.services.payment import PaymentService,IdempotencyConflictError

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(verify_api_key)],
)


payment_service = PaymentService()


@router.post(
    "",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_payment(
    data: PaymentCreateRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db),
):
    try:
        payment = await payment_service.create_payment(
            session=session,
            data=data,
            idempotency_key=idempotency_key,
        )

        return PaymentCreateResponse(
            payment_id=payment.id,
            status=payment.status,
            created_at=payment.created_at,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
)
async def get_payment(
    payment_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    payment = await payment_service.get_payment(
        session=session,
        payment_id=payment_id,
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return PaymentResponse(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.metadata_,
        status=payment.status,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
        webhook_sent_at=payment.webhook_sent_at,
    )
