import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import SessionLocal
from app.routers import auth, health, health_sync, sessions, telegram
from app.scheduler import start_background_tasks
from app.seed import seed_initial_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lifeos.main")

STATIC_DIR = Path(__file__).parent / "static"


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
app.include_router(auth.router)
app.include_router(sessions.router)

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    logger.warning(
        "app/static not found — web app UI not served (build it: `npm run build` "
        "in webapp/, or rebuild the Docker image). Telegram and /api routes still work."
    )
