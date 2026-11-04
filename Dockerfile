FROM node:20-alpine AS painel
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml requirements.lock ./
COPY backend ./backend
# versões travadas: uma atualização de biblioteca não quebra o build sem aviso
RUN pip install --no-cache-dir -r requirements.lock \
 && pip install --no-cache-dir --no-deps . \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
COPY --from=painel /web/dist ./frontend/dist
ENV PRECIM_DATABASE_URL=sqlite:////data/precim.db
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=6s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
