# Finance Tracker as one Docker image (a "multi-stage build").
# Stage 1 builds the React dashboard with Node. Stage 2 is a slim Python image that
# runs FastAPI and serves that built dashboard. Node is not in the final image.

# ---- Stage 1: build the frontend ----
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the app ----
FROM python:3.13-slim
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app/backend
# Install Python packages first, so this slow step is cached when only code changes.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# The real database lives on a mounted folder (/data), never inside the image.
ENV FINANCE_DB_URL=sqlite:////data/finance.db \
    PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000

# Bring the database up to date, then start the app with one worker (SQLite likes one writer).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
