import asyncio

from app.broker import consumer  # noqa: F401
from app.broker.connection import app


async def main() -> None:
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())