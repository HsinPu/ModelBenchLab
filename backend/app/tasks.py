import os
from celery import Celery
from sqlalchemy import select
from .db import Session, Item, init_db
from .execution import execute_item, recover_stale

celery = Celery('modelbenchlab', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
celery.conf.update(task_ignore_result=True, worker_prefetch_multiplier=1, task_acks_late=True, beat_schedule={'recover-and-dispatch': {'task': 'app.tasks.sweep', 'schedule': 30.0}})

@celery.task
def run_item(item_id):
    execute_item(item_id)

@celery.task
def sweep():
    init_db()
    recover_stale()
    with Session() as db:
        ids = db.scalars(select(Item.id).where(Item.status == 'queued').limit(500)).all()
    for item_id in ids: run_item.delay(item_id)
