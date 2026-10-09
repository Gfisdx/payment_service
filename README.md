# Payment Service

Асинхронный микросервис для создания и обработки платежей с использованием **FastAPI, PostgreSQL, RabbitMQ и SQLAlchemy 2.0**.

Сервис предоставляет REST API для создания и получения платежей, защищённый API-ключом. Обработка платежей выполняется асинхронно через RabbitMQ, а результаты отправляются клиенту с помощью вебхуков.

## Содержание

- [Возможности](#возможности)
- [Технологический стек](#технологический-стек)
- [Архитектура](#архитектура)
- [Требования](#требования)
- [Запуск проекта](#запуск-проекта)
- [Проверка работоспособности](#проверка-работоспособности)
- [API](#api)
- [Примеры запросов](#примеры-запросов)
- [Обработка платежей](#обработка-платежей)
- [Вебхуки](#вебхуки)
- [Тестирование](#тестирование)
- [Переменные окружения](#переменные-окружения)
- [Структура проекта](#структура-проекта)

## Возможности

- Создание платежей через REST API.
- Получение информации о платеже по идентификатору.
- Аутентификация запросов с помощью API-ключа.
- Поддержка ключей идемпотентности для защиты от повторного создания платежей.
- Асинхронная работа с PostgreSQL через SQLAlchemy 2.0.
- Передача задач на обработку через RabbitMQ.
- Фоновая обработка платежей отдельным consumer-процессом.
- Outbox-подход для надёжной передачи событий из PostgreSQL в RabbitMQ.
- Отправка вебхуков после обработки платежа.
- Повторные попытки отправки вебхуков.
- Миграции базы данных с помощью Alembic.
- Unit- и интеграционное тестирование с помощью pytest.

## Технологический стек

| Технология | Назначение |
|---|---|
| Python 3.12 | Основной язык |
| FastAPI | REST API |
| Pydantic v2 | Валидация данных |
| SQLAlchemy 2.0 | ORM и асинхронная работа с БД |
| PostgreSQL 17 | Хранение платежей и outbox-событий |
| RabbitMQ 4 | Очереди сообщений |
| FastStream / aio-pika | Работа с RabbitMQ |
| Alembic | Миграции базы данных |
| httpx | HTTP-запросы для вебхуков |
| uv | Управление зависимостями и окружением |
| Docker Compose | Запуск инфраструктуры и сервисов |
| pytest | Тестирование |

## Архитектура

```mermaid
flowchart TD
    Client[API Client] --> API[FastAPI]
    API --> DB[(PostgreSQL)]
    DB --> Outbox[Outbox Worker]
    Outbox --> MQ[RabbitMQ]
    MQ --> Consumer[Payment Consumer]
    Consumer --> Processor[Payment Processor]
    Processor --> DB
    Consumer --> Webhook[Webhook Client]
    Webhook --> External[External Service]
    Consumer --> Retry[Webhook Retry Queues]
    Retry --> Consumer
```

### Основные компоненты

- **API** — принимает запросы, проверяет API-ключ, валидирует данные и создаёт платежи.
- **PostgreSQL** — хранит платежи и события, ожидающие публикации.
- **Outbox Worker** — передаёт накопленные события в RabbitMQ.
- **RabbitMQ** — обеспечивает асинхронную передачу задач между компонентами.
- **Consumer** — получает сообщения, запускает обработку платежей и инициирует отправку вебхуков.
- **Payment Processor** — выполняет бизнес-логику обработки платежа.
- **Webhook Client** — отправляет HTTP-уведомления внешнему сервису.

Такое разделение позволяет не выполнять всю обработку внутри HTTP-запроса и независимо запускать API, обработчик сообщений и outbox-worker.

## Требования

Перед запуском установи:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) с поддержкой Docker Compose.
- Git — для клонирования репозитория.

Для запуска тестов вне Docker дополнительно потребуются Python 3.12 и [uv](https://docs.astral.sh/uv/).

## Запуск проекта

### 1. Клонирование репозитория

```bash
git clone <REPOSITORY_URL>
cd payment-service
```

Замени `<REPOSITORY_URL>` на URL своего GitHub-репозитория.

### 2. Настройка переменных окружения

Создай в корне проекта файл `.env`:

```dotenv
APP_NAME=payment-service
DEBUG=true

DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/payments

RABBITMQ_URL=amqp://rabbitmq:rabbitmq@rabbitmq:5672/

API_KEY=super-secret-api-key
WEBHOOK_TIMEOUT=5
```

Это пример конфигурации для локального запуска через Docker Compose. Внутри Docker-сети сервисы обращаются к PostgreSQL по имени `postgres`, а к RabbitMQ — по имени `rabbitmq`.

**Важно:** не добавляй настоящий `.env` в Git. Для репозитория используй `.env.example` с демонстрационными значениями.

### 3. Сборка контейнеров

```bash
docker compose build
```

### 4. Запуск сервисов

```bash
docker compose up -d
```

Команда запускает:

| Сервис | Назначение |
|---|---|
| `postgres` | База данных |
| `rabbitmq` | Брокер сообщений |
| `api` | REST API |
| `consumer` | Обработка сообщений |
| `outbox-worker` | Публикация outbox-событий |

PostgreSQL и RabbitMQ должны пройти healthcheck перед запуском зависимых сервисов.

### 5. Применение миграций

После запуска контейнеров выполни:

```bash
docker compose exec api uv run alembic upgrade head
```

Команда применит все доступные миграции Alembic к базе данных.

Если миграции завершились с ошибкой, сначала проверь состояние контейнера PostgreSQL и значение `DATABASE_URL`.

### 6. Проверка состояния контейнеров

```bash
docker compose ps
```

Просмотр логов API:

```bash
docker compose logs -f api
```

Просмотр логов consumer:

```bash
docker compose logs -f consumer
```

Просмотр логов outbox-worker:

```bash
docker compose logs -f outbox-worker
```

Просмотр логов PostgreSQL и RabbitMQ:

```bash
docker compose logs -f postgres rabbitmq
```

### 7. Остановка проекта

Остановить контейнеры, сохранив данные в Docker volumes:

```bash
docker compose down
```

Остановить контейнеры и удалить данные PostgreSQL и RabbitMQ:

```bash
docker compose down -v
```

**Внимание:** команда с `-v` удаляет данные в именованных volumes. Не используй её, если нужно сохранить платежи.

## Проверка работоспособности

После запуска открой:

| Ресурс | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| RabbitMQ Management | http://localhost:15672 |

Для RabbitMQ в приведённой конфигурации используются демонстрационные учётные данные:

```text
Username: rabbitmq
Password: rabbitmq
```

В Swagger можно просмотреть доступные эндпоинты, их параметры, схемы запросов и ответов, а также выполнить запросы вручную.

## API

Все защищённые эндпоинты требуют API-ключ в заголовке:

```http
X-API-Key: super-secret-api-key
```

При создании платежа также передаётся ключ идемпотентности:

```http
Idempotency-Key: order-12345
```

Ключ идемпотентности должен идентифицировать одну логическую операцию создания платежа. При повторной отправке того же запроса с тем же ключом ожидаемое поведение — не создавать второй платеж. Точное поведение при повторе зависит от реализации и должно проверяться тестами.

### Создание платежа

```http
POST /payments
```

Пример тела запроса:

```json
{
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Payment for order #12345",
  "metadata": {
    "order_id": "12345",
    "customer_id": "user-100"
  },
  "webhook_url": "https://example.com/webhooks/payments"
}
```

Поля запроса:

| Поле | Тип | Описание |
|---|---|---|
| `amount` | Decimal | Сумма платежа, больше нуля, не более двух знаков после десятичного разделителя |
| `currency` | Enum | Валюта: `RUB`, `USD` или `EUR` |
| `description` | String или `null` | Описание платежа |
| `metadata` | Object | Дополнительные данные |
| `webhook_url` | URL | Адрес для отправки результата обработки |

Пример ответа при создании:

```json
{
  "payment_id": "b5d7e92c-52c1-4a78-a4a4-24f76cb2f1c8",
  "status": "pending",
  "created_at": "2026-10-09T10:00:00Z"
}
```

Идентификатор и дата в примере демонстрационные. Фактические значения генерируются приложением.

### Получение платежа

```http
GET /payments/{payment_id}
```

Вместо `{payment_id}` передаётся UUID платежа.

Пример ответа:

```json
{
  "payment_id": "b5d7e92c-52c1-4a78-a4a4-24f76cb2f1c8",
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Payment for order #12345",
  "metadata": {
    "order_id": "12345",
    "customer_id": "user-100"
  },
  "status": "succeeded",
  "webhook_url": "https://example.com/webhooks/payments",
  "created_at": "2026-10-09T10:00:00Z",
  "processed_at": "2026-10-09T10:00:02Z",
  "webhook_sent_at": "2026-10-09T10:00:03Z"
}
```

Возможные статусы платежа:

- `pending` — ожидает обработки.
- `succeeded` — обработка завершилась успешно.
- `failed` — обработка завершилась ошибкой.

Поскольку обработка асинхронная, сразу после создания платеж может иметь статус `pending`. При следующем запросе статус может уже измениться.

## Примеры запросов

### Создание платежа через curl

```bash
curl -X POST "http://localhost:8000/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: super-secret-api-key" \
  -H "Idempotency-Key: order-12345" \
  -d '{
    "amount": "1500.00",
    "currency": "RUB",
    "description": "Payment for order #12345",
    "metadata": {
      "order_id": "12345"
    },
    "webhook_url": "https://example.com/webhooks/payments"
  }'
```

Сохрани значение `payment_id` из ответа.

### Получение платежа через curl

```bash
curl "http://localhost:8000/payments/b5d7e92c-52c1-4a78-a4a4-24f76cb2f1c8" \
  -H "X-API-Key: super-secret-api-key"
```

Замени UUID в URL на фактический `payment_id`.

### Создание платежа в PowerShell

В Windows PowerShell можно использовать `Invoke-RestMethod`:

```powershell
$headers = @{
    "X-API-Key" = "super-secret-api-key"
    "Idempotency-Key" = "order-12345"
}

$body = @{
    amount = "1500.00"
    currency = "RUB"
    description = "Payment for order #12345"
    metadata = @{
        order_id = "12345"
    }
    webhook_url = "https://example.com/webhooks/payments"
} | ConvertTo-Json -Depth 5

$response = Invoke-RestMethod `
    -Uri "http://localhost:8000/payments" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body

$response
```

Получение созданного платежа:

```powershell
$paymentId = $response.payment_id

Invoke-RestMethod `
    -Uri "http://localhost:8000/payments/$paymentId" `
    -Method Get `
    -Headers @{ "X-API-Key" = "super-secret-api-key" }
```

### Проверка API-ключа

Запрос без API-ключа:

```bash
curl -i "http://localhost:8000/payments"
```

Для защищённого эндпоинта ожидается отказ в доступе. Точный HTTP-статус зависит от реализации аутентификации.

Для проверки используй существующий эндпоинт и валидный UUID, если тестируешь получение платежа.

## Обработка платежей

После создания платежа обработка выполняется асинхронно:

1. API принимает запрос и сохраняет платеж в PostgreSQL.
2. Вместе с бизнес-изменением сохраняется outbox-событие.
3. Outbox Worker публикует событие в RabbitMQ.
4. Consumer получает сообщение и запускает Payment Processor.
5. Результат обработки сохраняется в PostgreSQL.
6. Consumer отправляет вебхук на адрес, указанный в `webhook_url`.
7. При ошибке отправки вебхука запускается предусмотренный механизм повторных попыток.


## Вебхуки

После обработки платежа сервис отправляет HTTP POST-запрос на указанный `webhook_url`.

Пример тела вебхука:

```json
{
  "payment_id": "b5d7e92c-52c1-4a78-a4a4-24f76cb2f1c8",
  "status": "succeeded",
  "amount": "1500.00",
  "currency": "RUB"
}
```

Вебхук содержит:

| Поле | Тип | Описание |
|---|---|---|
| `payment_id` | String | UUID платежа |
| `status` | String | Итоговый статус |
| `amount` | String | Сумма платежа |
| `currency` | String | Валюта |

В текущем формате вебхука `description` и `metadata` не передаются.

При успешном HTTP-ответе сервис фиксирует время отправки вебхука в `webhook_sent_at`. При сетевой ошибке или неуспешном HTTP-ответе отправка может быть повторена согласно настройкам очередей и логике consumer.


## Тестирование

### Установка зависимостей

Для локального запуска тестов установи зависимости проекта вместе с dev-группой:

```bash
uv sync --dev
```

### Настройка тестового окружения

Создай `.env.tests`:

```dotenv
APP_NAME=payment-service
DEBUG=true

DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/payments
RABBITMQ_URL=amqp://rabbitmq:rabbitmq@127.0.0.1:5672/

API_KEY=super-secret-api-key
WEBHOOK_TIMEOUT=2
WEBHOOK_URL=http://api:8000/test/webhook
```

Эти адреса рассчитаны на запуск pytest на хост-машине при опубликованных Docker-портах PostgreSQL и RabbitMQ.

**Важно:** `http://api:8000` — имя сервиса, доступное внутри сети Docker Compose. Если тестовый код или тестовый вебхук запускается непосредственно на хосте, такой URL может быть недоступен. В этом случае используй адрес, достижимый из процесса, который принимает вебхук, и согласуй его с тем, где запускается consumer.

Убедись, что PostgreSQL и RabbitMQ запущены:

```bash
docker compose up -d postgres rabbitmq
```

При необходимости примени миграции к тестовой базе, используя соответствующий тестовый конфиг.

### Запуск тестов

```bash
uv run pytest -v
```

Запуск конкретного файла:

```bash
uv run pytest tests/test_payments.py -v
```

Запуск интеграционных тестов, если они помечены маркером `integration`:

```bash
uv run pytest -m integration -v
```

### Запуск тестов внутри Docker

В текущем Dockerfile зависимости устанавливаются командой `uv sync --frozen --no-install-project`. Если dev-зависимости не устанавливаются в образ, pytest внутри контейнера может отсутствовать.

Для запуска тестов внутри контейнера необходимо включить dev-группу в установку зависимостей либо использовать отдельный Docker-образ для тестирования.

## Переменные окружения

| Переменная | Назначение | Пример |
|---|---|---|
| `APP_NAME` | Имя приложения | `payment-service` |
| `DEBUG` | Режим отладки | `true` |
| `DATABASE_URL` | URL PostgreSQL | `postgresql+asyncpg://...` |
| `RABBITMQ_URL` | URL RabbitMQ | `amqp://...` |
| `API_KEY` | Ключ доступа к API | `super-secret-api-key` |
| `WEBHOOK_TIMEOUT` | Таймаут HTTP-запроса вебхука в секундах | `5` |
| `WEBHOOK_URL` | Адрес тестового вебхука, если используется тестовой конфигурацией | `http://api:8000/test/webhook` |



