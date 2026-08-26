FROM python:3.12.13-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE constraints.txt ./
COPY src ./src

RUN python -m pip install --constraint constraints.txt hatchling==1.32.0 setuptools==84.0.0 \
    && python -m pip wheel \
        --no-build-isolation \
        --constraint constraints.txt \
        --wheel-dir /wheels \
        . \
    && python -m pip install \
        --no-index \
        --find-links=/wheels \
        --prefix=/install \
        telegram-for-codex==0.2.1

FROM python:3.12.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    TELEGRAM_DATA_DIR=/data/telegram \
    TELEGRAM_SESSION_PATH=/data/telegram/codex \
    TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string \
    TELEGRAM_AUDIT_LOG_PATH=/data/telegram/audit.jsonl

RUN groupadd --gid 10001 telegram \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --home-dir /nonexistent \
        --shell /usr/sbin/nologin \
        telegram \
    && install -d -m 0700 -o telegram -g telegram /data/telegram

COPY --from=builder /install /usr/local

WORKDIR /app
USER 10001:10001

VOLUME ["/data/telegram"]
EXPOSE 8000

ENTRYPOINT ["python", "-m", "telegram_codex.container_entrypoint"]
CMD ["telegram-codex-remote"]
