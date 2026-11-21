# syntax=docker/dockerfile:1
# ---------- Stage 1: builder -------------------------------------------------
# Has pip + everything needed to install dependencies. Nothing from this stage
# except the finished virtualenv reaches the final image, so pip caches and
# build leftovers stay out of it (that is the point of a multi-stage build).
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
# Copy ONLY requirements first: Docker caches this layer, so editing app code
# does not trigger a slow re-install of litellm and friends.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt

# ---------- Stage 2: test (build with: --target test) -------------------------
# Same venv + dev tools + tests. Used by `make test`; never shipped.
FROM builder AS test
RUN pip install -r requirements-dev.txt
WORKDIR /app
COPY app ./app
COPY tests ./tests
COPY pytest.ini .
CMD ["python", "-m", "pytest", "-q"]

# ---------- Stage 3: runtime (default target = last stage) --------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    DATABASE_URL=sqlite:////data/app.db
# Non-root user. /data is created and OWNED by that user in the image: when a
# fresh named volume is mounted at /data, Docker copies this ownership into it,
# so SQLite can create app.db without any chmod hacks.
RUN useradd --system --uid 10001 --no-create-home app \
 && mkdir /data && chown app:app /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app ./app
# The entrypoint fixes /data ownership, then drops to the non-root user (see the script).
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Hosting platforms (Render, Railway, ...) tell us which port to listen on via $PORT;
# locally it is unset and we use 8000.
ENV PORT=8000
EXPOSE 8000
# Marks the container "healthy" only when /health answers 200 (DB reachable + keys loaded).
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=4)"
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
