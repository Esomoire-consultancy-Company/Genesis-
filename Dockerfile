FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY genesis_contract.py genesis_http.py main.py start.sh ./
RUN chmod 0755 /app/start.sh

EXPOSE 8080

CMD ["./start.sh"]
