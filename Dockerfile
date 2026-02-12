FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

ARG APP_USER=app
ARG APP_UID=10001
ARG APP_GID=10001

RUN groupadd --gid "${APP_GID}" "${APP_USER}" \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin "${APP_USER}"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY --chown=${APP_UID}:${APP_GID} pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=${APP_UID}:${APP_GID} src ./src

USER ${APP_UID}:${APP_GID}

CMD ["uv", "run", "bot"]
