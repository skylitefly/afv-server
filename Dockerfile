FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md /app/
COPY afv_server /app/afv_server

RUN pip install --no-cache-dir .

EXPOSE 5000/tcp
EXPOSE 50000/udp

CMD ["python", "-m", "afv_server"]
