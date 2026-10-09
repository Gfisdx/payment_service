from faststream.rabbit import (
    ExchangeType,
    RabbitExchange,
    RabbitQueue,
)



# PAYMENT EXCHANGE


PAYMENTS_EXCHANGE = RabbitExchange(
    name="payments",
    type=ExchangeType.DIRECT,
    durable=True,
)


# 
# PAYMENT DEAD LETTER EXCHANGE
# 

PAYMENTS_DLX = RabbitExchange(
    name="payments.dlx",
    type=ExchangeType.DIRECT,
    durable=True,
)


# 
# MAIN PAYMENT QUEUE
# 
#
# Единственная очередь, которую слушает consumer.
#
# Новый payment:
#
# payments exchange
#        ↓
# payments.new
#        ↓
# ONE CONSUMER
#
# 

PAYMENTS_QUEUE = RabbitQueue(
    name="payments.new",
    durable=True,
    routing_key="payments.new",
)


# 
# WEBHOOK RETRY #1
# 
#
# Первая ошибка webhook:
#
# payments.new
#      ↓
# webhook.retry.1
#      ↓ TTL 1 sec
# payments.new
#
# 

WEBHOOK_RETRY_1 = RabbitQueue(
    name="webhook.retry.1",
    durable=True,
    routing_key="webhook.retry.1",
    arguments={
        "x-message-ttl": 1_000,
        "x-dead-letter-exchange": "payments",
        "x-dead-letter-routing-key": "payments.new",
    },
)


# 
# WEBHOOK RETRY #2
# 
#
# Вторая ошибка webhook:
#
# payments.new
#      ↓
# webhook.retry.2
#      ↓ TTL 2 sec
# payments.new
#
# 

WEBHOOK_RETRY_2 = RabbitQueue(
    name="webhook.retry.2",
    durable=True,
    routing_key="webhook.retry.2",
    arguments={
        "x-message-ttl": 2_000,
        "x-dead-letter-exchange": "payments",
        "x-dead-letter-routing-key": "payments.new",
    },
)


# 
# WEBHOOK RETRY #3
# 
#
# Последняя retry-очередь.
#
# После TTL сообщение НЕ возвращается
# в payments.new.
#
# Оно отправляется:
#
# webhook.retry.3
#        ↓ TTL 4 sec
# payments.dlx
#        ↓
# payments.dlq
#
# 

WEBHOOK_RETRY_3 = RabbitQueue(
    name="webhook.retry.3",
    durable=True,
    routing_key="webhook.retry.3",
    arguments={
        "x-message-ttl": 4_000,
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": "payments.dlq",
    },
)


# 
# PAYMENT DEAD LETTER QUEUE
# 
#
# Сюда попадают webhook-сообщения,
# которые не удалось доставить после всех попыток.
#
# 

PAYMENTS_DLQ = RabbitQueue(
    name="payments.dlq",
    durable=True,
    routing_key="payments.dlq",
)