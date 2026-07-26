FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/researcher

COPY pyproject.toml README.md ./

# Install dependencies (including the ~large CPU torch wheel, needed
# transitively by sentence-transformers) before copying application code.
# hatchling's editable install only needs the "app" package directory to
# exist to resolve metadata -- it doesn't need real contents yet, since an
# editable install just points back at this path and is resolved at import
# time, not install time. Placing this layer before `COPY app ./app` means
# editing application source no longer invalidates it, so a routine code
# change + rebuild no longer re-downloads torch from scratch.
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir torch \
      --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e .

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
