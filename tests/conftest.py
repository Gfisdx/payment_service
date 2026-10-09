import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.broker.connection import broker
from app.db.session import AsyncSessionLocal
from app.main import app

import os
from dotenv import load_dotenv

load_dotenv("env.tests", override=True)

WEBHOOK_URL = os.getenv("WEBHOOK_URL","http://api:8000/test/webhook")
API_KEY = os.getenv("API_KEY", "super-secret-api-key")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rabbitmq:rabbitmq@localhost:5672/")


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def rabbit_broker():
    await broker.start()

    try:
        yield broker
    finally:
        await broker.stop()