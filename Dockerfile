FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md .env.example requirements.runtime.lock ./
COPY src ./src
COPY frontend ./frontend
RUN pip install --no-cache-dir -r requirements.runtime.lock && pip install --no-cache-dir --no-deps .
RUN useradd --create-home appuser
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
ENV PYTHONPATH=/app/src DATABASE_PATH=/app/data/catalogue.db PARSER_MODE=offline
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
CMD ["sh", "-c", "python -m vehicle_search.seed --count 300 --seed 42 && exec uvicorn vehicle_search.api:app --host 0.0.0.0 --port 8000"]
