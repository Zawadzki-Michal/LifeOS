import logging

from fastapi import FastAPI

from app.routers import health, telegram

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="LifeOS")

app.include_router(health.router)
app.include_router(telegram.router)
