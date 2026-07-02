FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIXIVDOWNLOADER_RUNTIME=docker \
    PIXIVDOWNLOADER_HOST=0.0.0.0 \
    PIXIVDOWNLOADER_PORT=7653

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY config ./config
COPY resources ./resources
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 7653

CMD ["python", "-m", "backend.app"]
