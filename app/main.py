"""The app. Run with:  uvicorn app.main:app"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.ai.face_engine import FaceEngine
from app.api.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = FaceEngine()  # load the models once; every request reuses them
    yield


app = FastAPI(title="Face Attendance", lifespan=lifespan)
app.include_router(router)
# Mounted last: the API routes above are matched first, everything else is the frontend (index.html at "/").
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="frontend")
