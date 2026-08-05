FROM python:3.12-slim-bookworm

ARG YTARCHIVE_VERSION=v0.5.0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul \
    HOST=0.0.0.0 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        aria2 \
        ca-certificates \
        curl \
        ffmpeg \
        tini \
        tzdata \
        yt-dlp \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

RUN curl -fsSL -o /usr/local/bin/ytarchive \
        "https://github.com/Kethsar/ytarchive/releases/download/${YTARCHIVE_VERSION}/ytarchive-linux-amd64" \
    && chmod +x /usr/local/bin/ytarchive

COPY . .

RUN mkdir -p /app/chzzk /app/json /app/logs /app/tmp/ytarchive

EXPOSE 5000
VOLUME ["/app/json", "/app/chzzk", "/app/logs"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "app_entry.py"]
