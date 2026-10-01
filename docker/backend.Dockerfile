FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen
ENV PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
RUN uv run playwright install --with-deps chromium
COPY backend/ ./
COPY tests/ /tests/
RUN useradd --uid 10001 --create-home app && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
