from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.core.config import settings

broker = RabbitBroker(
    settings.rabbitmq_url,
)


app = FastStream(broker)
