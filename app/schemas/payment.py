from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.db.models.payment import Currency, PaymentStatus


class PaymentCreateRequest(BaseModel):
    amount: Decimal = Field(
        gt=0,
        decimal_places=2,
    )

    currency: Currency

    description: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    webhook_url: AnyHttpUrl


class PaymentCreateResponse(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    created_at: datetime


class PaymentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    payment_id: UUID
    amount: Decimal
    currency: Currency
    description: str | None

    metadata: dict[str, Any] = Field(
        validation_alias="metadata_",
        serialization_alias="metadata",
    )

    status: PaymentStatus
    webhook_url: AnyHttpUrl
    created_at: datetime
    processed_at: datetime | None
    webhook_sent_at: datetime | None
