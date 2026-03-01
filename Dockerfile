FROM python:3.13-slim

RUN useradd -m -s /bin/bash minion

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/

RUN chown -R minion:minion /app
USER minion

CMD ["uv", "run", "python", "-m", "src.main"]
