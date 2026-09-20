FROM python:3.14-slim AS base
WORKDIR /app

FROM base AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

RUN pip install --quiet --root-user-action=ignore uv
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ARG TAILWIND_VERSION=v4.3.3

RUN curl -sLO "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64" \
    && chmod +x tailwindcss-linux-x64 \
    && mv tailwindcss-linux-x64 /usr/local/bin/tailwindcss

FROM base AS runner

RUN groupadd --system app && useradd --system --gid app --create-home app

ARG PRODUCTION=True

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PRODUCTION=${PRODUCTION}

# Dummy env variables for build time
ENV DB_PASSWORD="your_db_password"
ENV DJANGO_SECRET_KEY="your_django_secret_key"

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /usr/local/bin/tailwindcss /usr/local/bin/tailwindcss
COPY --chown=app:app . .

RUN chmod +x scripts/entrypoint.sh

RUN /usr/local/bin/tailwindcss -i ./apps/theme/static_src/src/styles.css \
    -o ./apps/theme/static/css/dist/styles.css --minify
RUN python manage.py collectstatic --noinput

RUN chown -R app:app /app

USER app

EXPOSE 80

ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--capture-output", "config.wsgi:application"]