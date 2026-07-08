FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JAVSCRAPER_MODE=service \
    JAVSCRAPER_HOST=0.0.0.0 \
    JAVSCRAPER_PORT=8765 \
    JAVSCRAPER_DISABLE_BROWSER=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY --chown=appuser:appuser app.py /app/app.py
COPY --chown=appuser:appuser javscraper /app/javscraper
COPY --chown=appuser:appuser webui /app/webui

USER appuser

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/emby-api/v1/health', timeout=3); sys.exit(0)"

CMD ["python3", "app.py"]
