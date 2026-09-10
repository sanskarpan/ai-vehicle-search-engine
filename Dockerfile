FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md .env.example ./
COPY src ./src
COPY frontend ./frontend
RUN pip install --no-cache-dir .
RUN useradd --create-home appuser
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
ENV PYTHONPATH=/app/src DATABASE_PATH=/app/data/catalogue.db PARSER_MODE=offline
EXPOSE 8000
CMD ["sh", "-c", "python -m vehicle_search.seed --count 300 --seed 42 && uvicorn vehicle_search.api:app --host 0.0.0.0 --port 8000"]
