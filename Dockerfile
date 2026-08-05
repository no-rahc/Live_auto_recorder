FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        streamlink \
        yt-dlp \
        aria2 \
        tzdata \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade streamlink \
    && pip install --no-cache-dir -r requirements.txt

# Install ytarchive binary (not available on PyPI)
ARG YTARCHIVE_VERSION=v0.5.0
RUN curl -L -o /usr/local/bin/ytarchive \
        "https://github.com/Kethsar/ytarchive/releases/download/${YTARCHIVE_VERSION}/ytarchive-linux-amd64" \
    && chmod +x /usr/local/bin/ytarchive

COPY . .

RUN mkdir -p /app/chzzk /app/tmp/ytarchive

EXPOSE 5000

CMD ["python", "Live Auto Recorder.py"]