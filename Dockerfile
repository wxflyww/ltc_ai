# ---- builder ----
FROM python:3.11-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir .

# ---- runtime ----
FROM python:3.11-slim AS runtime
RUN useradd -m -u 1000 appuser
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LTC_ENV=dev
WORKDIR /app
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health'); sys.exit(0)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
