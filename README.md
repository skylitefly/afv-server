# AFV Server

AFV-compatible audio server.
## Run

```powershell
cd afv-server
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m afv_server
```

## Docker

Build locally:

```powershell
cd afv-server
docker build -t skylite-afv-server .
```

Run with Docker Compose:

```powershell
cd afv-server
docker compose up -d
```

For remote clients, set `AFV_PUBLIC_VOICE_HOST` in `docker-compose.yml` to the
public IP or DNS name that pilot clients can reach over UDP port `50000`.

By default, authentication is permissive for local testing. To delegate auth to
the existing web backend:

```powershell
$env:AFV_AUTH_MODE = "webhook"
$env:AFV_AUTH_WEBHOOK_URL = "https://portal.skylitefly.com/api/auth/pyfsd-auth/"
$env:AFV_AUTH_WEBHOOK_SECRET = "<same REQUEST_SIGNING_SECRET as web-backend>"
python -m afv_server
```

## Configuration

| Environment Variable | Default | Purpose |
| --- | --- | --- |
| `AFV_HTTP_HOST` | `0.0.0.0` | HTTP bind host |
| `AFV_HTTP_PORT` | `5000` | HTTP API port |
| `AFV_UDP_HOST` | `0.0.0.0` | UDP bind host |
| `AFV_UDP_PORT` | `50000` | UDP voice port |
| `AFV_PUBLIC_VOICE_HOST` | auto local IP | Host returned to pilot clients |
| `AFV_PUBLIC_VOICE_PORT` | `AFV_UDP_PORT` | UDP port returned to pilot clients |
| `AFV_AUTH_MODE` | `allow` | `allow` or `webhook` |
| `AFV_AUTH_WEBHOOK_URL` | empty | web-backend auth endpoint |
| `AFV_AUTH_WEBHOOK_SECRET` | empty | optional HMAC request signing secret |
| `AFV_TOKEN_TTL_SECONDS` | `3600` | AFV API JWT lifetime |
| `AFV_STATIONS_FILE` | empty | JSON list for `/api/v1/stations/aliased` |
