FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tashkent

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Ma'lumotlar bazasi shu papkada saqlanadi (volume sifatida ulanadi)
RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
