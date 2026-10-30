# Stage 1: build the React frontend
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI app serving the built frontend from the same origin
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend/dist \
    LOG_FILE_PATH=/tmp/relay.jsonl
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
EXPOSE 8000
# Apply migrations, then start. SEED_DEMO_DATA=true seeds only an empty database.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
