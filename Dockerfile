FROM node:20-alpine AS painel
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir . \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
COPY --from=painel /web/dist ./frontend/dist
ENV PRECIM_DATABASE_URL=sqlite:////data/precim.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
