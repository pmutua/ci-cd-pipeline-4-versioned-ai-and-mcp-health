# Dockerfile - Deliverable 2. Slim base image, dependency layer ordered
# ahead of the code layer so an edit to app/ or mcp_server/ reuses the
# cached pip install and rebuilds in seconds instead of minutes.
#
# Build from the REPO ROOT (this file's own directory):
#   docker build -t afyaplus-platform:1.0.0 .
#
# Secrets (JWT_SECRET, OPENAI_API_KEY, ...) are never baked into this
# image -- app/auth.py and app/triage_model.py read them from the process
# environment at runtime. Run with:
#   docker run --rm -p 8000:8000 --env-file .env afyaplus-platform:1.0.0

FROM python:3.12-slim

WORKDIR /app

# Dependencies before code: this layer only invalidates when
# requirements-api.txt changes.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Code layer -- the one that changes on every edit.
COPY app/ ./app/
COPY mcp_server/ ./mcp_server/

# Non-root user -- same UID (10001) the read-only deployment.yaml's
# securityContext already assumes, so the image and the manifest agree.
# logs/ is pre-created and owned by that user because app/main.py and
# mcp_server/logistics_mcp.py both write log files under /app/logs at
# runtime, after the process has dropped root.
RUN groupadd --gid 10001 afyaplus \
    && useradd --uid 10001 --gid afyaplus --no-create-home --shell /usr/sbin/nologin afyaplus \
    && mkdir -p /app/logs \
    && chown -R afyaplus:afyaplus /app
USER 10001

EXPOSE 8000

# Same unprotected route app/auth.py's routes deliberately leave open --
# an orchestrator (or this HEALTHCHECK) never needs credentials to ask
# "are you alive?".
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
