# Dockerfile - Deliverable 2. Slim base image, dependency layer ordered
# ahead of the code layer so an edit to app/ or logistics_mcp_versioned.py
# reuses the cached pip install and rebuilds in seconds instead of minutes.
#
# Build from the REPO ROOT (this file's own directory), tagging so the
# image tag, the prompt bundle, and the MCP server version all align (see
# Deliverable 1 / runbook.md "Tag alignment"):
#   docker build -t afyaplus-platform:1.3.0-candidate --build-arg IMAGE_TAG=1.3.0-candidate .
#
# Secrets (JWT_SECRET, OPENAI_API_KEY, ...) are never baked into this
# image -- app/auth.py and app/triage_model.py read them from the process
# environment at runtime. Run with:
#   docker run --rm -p 8000:8000 --env-file .env afyaplus-platform:1.3.0-candidate

FROM python:3.12-slim

WORKDIR /app

# Dependencies before code: this layer only invalidates when
# requirements-api.txt changes.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Code + versioned artefacts layer -- the one that changes on every edit.
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/
COPY logistics_mcp_versioned.py ab_prompt_flag.py tool_metrics.py clinics.json check_prompt_pin.py ./

# IMAGE_TAG is baked in as a build arg -> env var so GET /health can report
# exactly which release this running container is, aligned with the git
# tag and the image tag a human reads off `docker images`.
ARG IMAGE_TAG=dev
ENV IMAGE_TAG=${IMAGE_TAG}

# Non-root user -- same UID (10001) a read-only deployment's
# securityContext would already assume, so the image and the manifest
# agree. logs/ is pre-created and owned by that user because app/main.py
# and logistics_mcp_versioned.py both write log files under /app/logs at
# runtime, after the process has dropped root.
RUN groupadd --gid 10001 afyaplus \
    && useradd --uid 10001 --gid afyaplus --no-create-home --shell /usr/sbin/nologin afyaplus \
    && mkdir -p /app/logs \
    && chown -R afyaplus:afyaplus /app
USER 10001

EXPOSE 8000

# Same unprotected route app/auth.py's routes deliberately leave open --
# an orchestrator (or this HEALTHCHECK) never needs credentials to ask
# "are you alive, and what version are you?".
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
