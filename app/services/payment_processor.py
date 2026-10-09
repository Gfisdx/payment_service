import asyncio
import random


class PaymentProcessingError(Exception):
    pass


async def process_payment() -> bool:
    await asyncio.sleep(random.uniform(2, 5))
    

    if random.random() >= 0.9:
        raise PaymentProcessingError("Payment processing failed")
    