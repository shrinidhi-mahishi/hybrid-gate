FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p data

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV DATA_DIR=data
ENV ENFORCE_HYBRID_GATE=true
ENV USE_LLM=false

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
