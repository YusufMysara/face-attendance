FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENCV_FOR_THREADS_NUM=1 \
    PORT=8000

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY models_opencv ./models_opencv

# Do not run as root inside the container.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# OPENCV_FOR_THREADS_NUM=1: OpenCV would start one thread per host core; under a 1-CPU limit
# they throttle each other (measured: 3x slower). PORT: hosts such as Railway set it themselves.
# Bring the database schema up to date, then start the server.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
