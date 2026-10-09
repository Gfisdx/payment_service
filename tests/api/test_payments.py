from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

from tests.conftest import API_KEY, WEBHOOK_URL


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_create_payment(client):
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "amount": "100.00",
            "currency": "RUB",
            "description": "Test payment",
            "metadata": {
                "order_id": "123",
            },
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 202

    data = response.json()

    assert "payment_id" in data
    assert data["status"] == "pending"
    assert "created_at" in data
    
    
@pytest.mark.asyncio
async def test_get_payment(client):
    idempotency_key = str(uuid4())

    create_response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": idempotency_key,
        },
        json={
            "amount": "250.50",
            "currency": "USD",
            "description": "Test payment",
            "metadata": {
                "order_id": "456",
            },
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert create_response.status_code == 202

    payment_id = create_response.json()["payment_id"]

    response = await client.get(
        f"/api/v1/payments/{payment_id}",
        headers={
            "X-API-Key": API_KEY,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["payment_id"] == payment_id
    assert data["amount"] == "250.50"
    assert data["currency"] == "USD"
    assert data["description"] == "Test payment"
    assert data["status"] == "pending"
    assert data["webhook_url"] == "https://example.com/webhook"
    assert data["metadata"] == {
        "order_id": "456",
    }
    
    
@pytest.mark.asyncio
async def test_get_payment_not_found(client):
    payment_id = uuid4()

    response = await client.get(
        f"/api/v1/payments/{payment_id}",
        headers={
            "X-API-Key": API_KEY,
        },
    )

    assert response.status_code == 404

    data = response.json()

    assert data["detail"] == "Payment not found"
    
    
@pytest.mark.asyncio
async def test_create_payment_without_api_key(client):
    response = await client.post(
        "/api/v1/payments",
        headers={
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "amount": "100.00",
            "currency": "RUB",
            "description": "Test payment",
            "metadata": {},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code in (401, 403)
    

@pytest.mark.asyncio
async def test_create_payment_with_invalid_api_key(client):
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "wrong-key",
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "amount": "100.00",
            "currency": "RUB",
            "description": "Test payment",
            "metadata": {},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code in (401, 403)
    
    
@pytest.mark.asyncio
async def test_create_payment_idempotency(client):
    idempotency_key = str(uuid4())

    payload = {
        "amount": "100.00",
        "currency": "RUB",
        "description": "Idempotency test",
        "metadata": {
            "order_id": "999",
        },
        "webhook_url": "https://example.com/webhook",
    }

    headers = {
        "X-API-Key": API_KEY,
        "Idempotency-Key": idempotency_key,
    }

    first_response = await client.post(
        "/api/v1/payments",
        headers=headers,
        json=payload,
    )

    second_response = await client.post(
        "/api/v1/payments",
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202

    first_data = first_response.json()
    second_data = second_response.json()

    assert first_data["payment_id"] == second_data["payment_id"]
    assert first_data["status"] == second_data["status"]
    assert first_data["created_at"] == second_data["created_at"]
    
    
@pytest.mark.asyncio
async def test_create_payment_without_idempotency_key(client):
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
        },
        json={
            "amount": "100.00",
            "currency": "RUB",
            "description": "Test payment",
            "metadata": {},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 422
    
    
@pytest.mark.asyncio
async def test_create_payment_invalid_currency(client):
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "amount": "100.00",
            "currency": "KZT",
            "description": "Invalid currency",
            "metadata": {},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 422
    
    
@pytest.mark.asyncio
async def test_create_payment_negative_amount(client):
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "amount": "-100.00",
            "currency": "RUB",
            "description": "Invalid amount",
            "metadata": {},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 422
    

@pytest.mark.asyncio
async def test_get_payment_requires_api_key(client):
    # Создаём платёж с корректным API-ключом.
    create_response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": "test-get-payment-requires-api-key",
        },
        json={
            "amount": "1000.00",
            "currency": "RUB",
            "description": "API key authentication test",
            "webhook_url": WEBHOOK_URL,
        },
    )

    assert create_response.status_code == 202, create_response.text

    payment_id = create_response.json()["payment_id"]

    # Пытаемся получить платёж без API-ключа.
    response = await client.get(
        f"/api/v1/payments/{payment_id}",
    )

    assert response.status_code == 401
    

@pytest.mark.asyncio
async def test_get_payment_without_api_key(client):
    # Создаём платёж с корректным API-ключом.
    create_response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": "test-get-payment-without-api-key",
        },
        json={
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment",
            "webhook_url": WEBHOOK_URL,
        },
    )

    assert create_response.status_code == 202, create_response.text

    payment_id = create_response.json()["payment_id"]

    # Получаем платёж без API-ключа.
    response = await client.get(
        f"/api/v1/payments/{payment_id}",
    )

    assert response.status_code == 401
    

@pytest.mark.asyncio
async def test_get_payment_without_api_key(client):
    # Создаём платёж с корректным API-ключом.
    create_response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": "test-get-payment-without-api-key",
        },
        json={
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment",
            "webhook_url": WEBHOOK_URL,
        },
    )

    assert create_response.status_code == 202, create_response.text

    payment_id = create_response.json()["payment_id"]

    # Получаем платёж без API-ключа.
    response = await client.get(
        f"/api/v1/payments/{payment_id}",
    )

    assert response.status_code == 401