FROM python:3.11-slim

WORKDIR /app
RUN useradd --create-home --uid 10001 groundlink
COPY pyproject.toml README.md LICENSE ./
COPY core core
COPY agents agents
COPY telemetry telemetry
COPY dashboard dashboard
COPY demo demo
COPY scripts scripts
COPY data data
COPY prompts prompts
COPY room_templates room_templates
COPY alembic.ini alembic.ini
COPY alembic alembic
RUN pip install --no-cache-dir .
USER groundlink
EXPOSE 8090
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8090"]
