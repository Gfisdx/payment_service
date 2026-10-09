import asyncio
import logging

from app.broker.connection import broker
from app.broker.publisher import publish_outbox
from app.broker.topology import declare_topology


logger = logging.getLogger(__name__)


async def run() -> None:
    await broker.start()

    try:
        await declare_topology()

        while True:
            try:
                await publish_outbox(broker)

            except Exception:
                logger.exception("Outbox publishing failed")

            await asyncio.sleep(1)

    finally:
        await broker.close()


if __name__ == "__main__":
    asyncio.run(run())