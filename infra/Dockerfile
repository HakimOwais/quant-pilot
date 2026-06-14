FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg[binary] ships libpq in the wheel, so no system build deps are required.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e .

# Run as non-root.
RUN useradd --create-home app && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "quant_pilot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
