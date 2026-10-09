import httpx

from app.core.config import settings
from app.db.models.payment import Payment


class WebhookError(Exception):
    pass


async def send_payment_webhook(
    payment: Payment,
) -> None:

    payload = {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.webhook_timeout,
        ) as client:
            response = await client.post(
                payment.webhook_url,
                json=payload,
            )

            response.raise_for_status()


    except httpx.HTTPStatusError as exc:
        raise WebhookError(
            f"Webhook returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:500]}"
        ) from exc

    except httpx.RequestError as exc:
        raise WebhookError(
            f"Webhook request error: {exc}"
        ) from exc
