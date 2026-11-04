# The `engine` service: carbonstack's HTTP API, reached by the web app over
# Railway's private network. Built from the repository root
# (RAILWAY_DOCKERFILE_PATH=deploy/railway/engine.Dockerfile). The routes the
# web app calls compute without storing, so the database is scratch.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1 PORT=8000
CMD ["sh", "-c", "exec carbonstack --db /tmp/engine.db serve --host :: --port \"$PORT\""]
