# Builds the web app SPA into /repo/app/static (vite.config.js outDir), then
# copied into the final image below — one deployable image, no separate
# frontend service to run or remember to rebuild.
FROM node:20-alpine AS frontend

WORKDIR /repo/webapp
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webapp/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /repo/app/static ./app/static

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
