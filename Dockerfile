FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/researcher

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir torch \
      --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
