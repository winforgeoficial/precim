FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir .
ENV PRECIM_DATABASE_URL=sqlite:////data/precim.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
