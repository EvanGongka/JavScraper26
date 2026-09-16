FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    JAVSCRAPER_MODE=service \
    JAVSCRAPER_HOST=0.0.0.0 \
    JAVSCRAPER_PORT=8765 \
    JAVSCRAPER_DISABLE_BROWSER=1 \
    JAVSCRAPER_LOG_FILE=/var/log/javscraper/javscraper.log

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/log/javscraper \
    && chown -R appuser:appuser /var/log/javscraper

COPY requirements.txt /app/requirements.txt

RUN pip install --retries 10 --timeout 60 -r /app/requirements.txt

COPY --chown=appuser:appuser app.py /app/app.py
COPY --chown=appuser:appuser javscraper /app/javscraper
COPY --chown=appuser:appuser webui /app/webui
COPY --chown=appuser:appuser docker/healthcheck.py /app/docker/healthcheck.py

USER appuser

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "/app/docker/healthcheck.py"]

CMD ["python3", "app.py"]
