from celery import Celery
from .config import settings

celery = Celery("quality-worker", broker=settings.redis_url, backend=settings.redis_url)

@celery.task(name="quality.ping")
def ping(): return {"status":"ok"}

