# WOLF as a container, for hosting it online so it runs without your computer.
#
# Needs these environment variables (set them as secrets on your host):
#   ANTHROPIC_API_KEY   your Claude API key
#   WOLF_TOKEN          a long random password; your app link is https://<your-host>/?token=<WOLF_TOKEN>
# and a persistent disk mounted at /data (that's where WOLF's memory of you lives).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WOLF_HOME=/data \
    WOLF_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app
COPY pyproject.toml README.md ./
COPY wolf ./wolf
COPY wolf_assistant ./wolf_assistant
RUN pip install --no-cache-dir . && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8080
CMD ["wolf", "serve"]
