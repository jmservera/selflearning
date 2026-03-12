FROM ghcr.io/astral-sh/uv:0.7 AS uv
FROM python:3.12-slim

WORKDIR /app

COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
