import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import SessionLocal
from app.routers import health, health_sync, telegram
from app.scheduler import start_background_tasks
from app.seed import seed_initial_data

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        seed_initial_data(db)
    tasks = start_background_tasks()
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="LifeOS", lifespan=lifespan)

app.include_router(health.router)
app.include_router(health_sync.router)
app.include_router(telegram.router)
