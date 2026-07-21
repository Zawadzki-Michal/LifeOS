import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import SessionLocal
from app.routers import health, telegram
from app.seed import seed_initial_data

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        seed_initial_data(db)
    yield


app = FastAPI(title="LifeOS", lifespan=lifespan)

app.include_router(health.router)
app.include_router(telegram.router)
