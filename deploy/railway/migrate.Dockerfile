# The `migrate` service: applies deploy/railway/bootstrap.sql and
# supabase/migrations to the Railway Postgres, then exits. Built from the
# repository root (RAILWAY_DOCKERFILE_PATH=deploy/railway/migrate.Dockerfile).
FROM postgres:17-alpine
RUN apk add --no-cache bash
COPY deploy/railway/bootstrap.sql deploy/railway/migrate.sh /deploy/
COPY supabase /supabase
CMD ["sh", "/deploy/migrate.sh"]
