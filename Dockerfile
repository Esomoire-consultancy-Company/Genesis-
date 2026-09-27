FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY genesis_contract.py genesis_runtime.py genesis_http.py main.py start.sh ./
RUN chmod 0755 /app/start.sh

EXPOSE 8080

CMD ["./start.sh"]
