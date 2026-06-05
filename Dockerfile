FROM python:3.12-slim

WORKDIR /app

# 依存関係
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt

# アプリ本体（.dockerignore で秘密情報は除外）
COPY deploy/ /app/deploy/
COPY scripts/ /app/scripts/
COPY CLAUDE.md /app/CLAUDE.md
COPY data/ /app/data/
COPY templates/ /app/templates/
COPY articles/ /app/articles/

ENV PYTHONPATH=/app:/app/scripts
ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "300", "deploy.wsgi:application"]
