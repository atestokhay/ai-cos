FROM python:3.12.16-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Holds uv and the runtime environment; uv never reaches the runtime image.
FROM base AS build
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN pip install --no-cache-dir --disable-pip-version-check uv==0.13.6
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM build AS dev
RUN uv sync --frozen
COPY alembic.ini ./
COPY apps ./apps
COPY core ./core
COPY migrations ./migrations
COPY tests ./tests
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin aicos
USER 10001
CMD ["uvicorn", "--factory", "apps.api.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "apps", "--reload-dir", "core"]

FROM base AS runtime
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin aicos
COPY --from=build /app/.venv ./.venv
COPY alembic.ini ./
COPY apps ./apps
COPY core ./core
COPY migrations ./migrations
USER 10001
CMD ["uvicorn", "--factory", "apps.api.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
