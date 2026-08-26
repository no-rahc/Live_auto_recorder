# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM golang:1.25-bookworm AS ytarchive-builder

ARG TARGETOS=linux
ARG TARGETARCH=amd64
ARG YTARCHIVE_VERSION=v0.5.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /out \
    && git clone --depth 1 --branch "${YTARCHIVE_VERSION}" \
        https://github.com/Kethsar/ytarchive.git /src/ytarchive \
    && cd /src/ytarchive \
    && CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
        go build -trimpath -ldflags="-s -w" -o /out/ytarchive .

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul \
    HOST=0.0.0.0 \
    PORT=5000 \
    RECORDINGS_ROOT=/app/chzzk \
    RCLONE_CONFIG=/app/json/rclone.conf

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        aria2 \
        ca-certificates \
        curl \
        ffmpeg \
        rclone \
        tini \
        tzdata \
        yt-dlp \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

COPY --from=ytarchive-builder /out/ytarchive /usr/local/bin/ytarchive
RUN chmod 0755 /usr/local/bin/ytarchive \
    && /usr/local/bin/ytarchive -V \
    && rclone version \
    && ffprobe -version >/dev/null

COPY app_entry.py live_auto_recorder.py VERSION ./
COPY lar_app ./lar_app
COPY module ./module
COPY templates ./templates
COPY dependent ./dependent
COPY LICENSE THIRD_PARTY_NOTICES.md ./

RUN mkdir -p /app/chzzk /app/json /app/logs /app/tmp/ytarchive \
    && python -m compileall -q app_entry.py lar_app module

EXPOSE 5000
VOLUME ["/app/json", "/app/chzzk", "/app/logs"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/readyz" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "app_entry.py"]
