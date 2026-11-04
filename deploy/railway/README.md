# Railway deployment

The whole product on one Railway project (`carbon-credits`, environment
`production`), with Railway Postgres as the database and Supabase's open-source
services running on top of it in place of a Supabase cloud project.

| Service | What it is | Built from |
|---|---|---|
| `Postgres` | Railway Postgres: every table, policy and file record | Railway template |
| `auth` | Supabase Auth (GoTrue): accounts, sessions, email links | `supabase/auth:v2.197.0` |
| `rest` | PostgREST: the API the app queries, under row-level security | `postgrest/postgrest:v13.0.7` |
| `storage` | Supabase Storage: evidence files, on the `storage-volume` volume | `supabase/storage-api:v1.89.6` |
| `migrate` | Applies `bootstrap.sql` and `supabase/migrations`, then exits | `migrate.Dockerfile` |
| `engine` | The carbonstack Python API (`/api/estimate`, `/api/forecast`, ...) | `engine.Dockerfile` |
| `web` | The Next.js app, and the only public service | `web/` (Railpack, `web/railway.json`) |

The older `carbon-credits` service in the same project (the dashboard,
deployed from GitHub) is separate and untouched.

## The address

**https://carobon-credit-production.up.railway.app** is the only address the
app uses. These variables all use it:

| Service | Variables |
|---|---|
| `web` | `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_SUPABASE_URL` |
| `auth` | `GOTRUE_SITE_URL`, `API_EXTERNAL_URL`, `GOTRUE_URI_ALLOW_LIST` (`<site>/**`) |

The first Railway domain, `web-production-c782e.up.railway.app`, is listed in
`LEGACY_HOSTS` on `web`. It answers with a permanent redirect (308) to the same
path and query on the canonical address, so old links keep working while
cookies and email links only ever live on one domain.

To move to another domain, such as a custom one:
1. Add the domain to `web`.
2. Change the five variables above to it.
3. Add the old domain to `LEGACY_HOSTS`.
4. Rebuild with `railway up web --path-as-root -s web`. `NEXT_PUBLIC_*` values
   are compiled in, so a variable change alone is not enough.
5. Redeploy `auth`.

## How requests flow

```
browser ──https──▶ web ──┬─ /auth/v1/*    ─▶ auth:9999
                         ├─ /rest/v1/*    ─▶ rest:3000 ──▶ Postgres
                         ├─ /storage/v1/* ─▶ storage:5000
                         └─ server actions ─▶ engine:8000 (bearer token)
```

- **Only `web` is public.** Its `next.config.ts` rewrites forward the three
  Supabase paths over the private network (`*.railway.internal`).
- **Email links and signed file URLs** reach `auth` and `storage` through those
  rewrites.
- **The app's own server** calls Supabase on loopback (`SUPABASE_INTERNAL_URL`).
  The browser never calls Supabase directly.

## Redeploying

Nothing deploys from GitHub. Upload from a checkout:

```bash
railway up web --path-as-root -s web --detach   # the app
railway up -s engine --detach                   # from the repository root
railway up -s migrate --detach                  # after adding a migration
```

After a deploy, run the end-to-end check. It signs up, sets up an
organisation, edits the profile, enrols a farm, gets an estimate from the
engine, then signs out and back in. It also checks that the legacy address
redirects:

```bash
python3 deploy/railway/e2e.py https://carobon-credit-production.up.railway.app \
    --legacy https://web-production-c782e.up.railway.app
```

Each run leaves a new `e2e-…@example.com` account and its
"E2E Farmers Collective" behind in the database.

`migrate` runs on every deploy and records what it applied in
`supabase_migrations.schema_migrations`, so re-running it is safe.

To run the row-level security tests against the deployed Postgres version:
1. Set `RUN_RLS_TESTS=1` on `migrate` and redeploy it. The tests use a scratch
   database (`carbonstack_rls_test`) that they drop afterwards.
2. Set `RUN_RLS_TESTS=0` again when they pass.

## Secrets

Generated once, stored only as Railway variables. Other services read them
through references such as `${{auth.GOTRUE_JWT_SECRET}}`, so each secret has
one home:

| Variable | Lives on | Used by |
|---|---|---|
| `GOTRUE_JWT_SECRET` | `auth` | `rest`, `storage` (sign and check every session token) |
| `AUTH_ADMIN_PASSWORD` | `auth` | `migrate` (the `supabase_auth_admin` login) |
| `AUTHENTICATOR_PASSWORD` | `rest` | `migrate` (the `authenticator` login) |
| `ANON_KEY`, `SERVICE_KEY` | `storage` | `web` reads `ANON_KEY`; both are JWTs signed with the secret above |
| `CARBONSTACK_TOKEN` | `engine` | `web` (`CARBONSTACK_ENGINE_TOKEN`) |

Rotating the JWT secret signs everyone out and needs new `ANON_KEY` and
`SERVICE_KEY` values.

## Not set up yet

- **Email.** There is no mail server, so `GOTRUE_MAILER_AUTOCONFIRM=true`:
  sign-ups are active immediately, without a confirmation email. Password
  reset, sign-in links and email changes cannot send, and the app says so.
  To turn email on:
  1. Set `GOTRUE_SMTP_HOST`, `GOTRUE_SMTP_PORT`, `GOTRUE_SMTP_USER`,
     `GOTRUE_SMTP_PASS` and `GOTRUE_SMTP_ADMIN_EMAIL` on `auth` (for example,
     from Resend or SES).
  2. Set `GOTRUE_MAILER_AUTOCONFIRM=false`.
- **Google sign-in.** Hidden with `AUTH_GOOGLE_ENABLED=false` on `web`. To turn
  it on:
  1. Set `GOTRUE_EXTERNAL_GOOGLE_ENABLED=true`, `GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID`,
     `GOTRUE_EXTERNAL_GOOGLE_SECRET` and
     `GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI=https://carobon-credit-production.up.railway.app/auth/v1/callback`
     on `auth`.
  2. Remove `AUTH_GOOGLE_ENABLED` from `web`.
- **Backups.** Turn on Railway's Postgres backups for both `postgres-volume`
  and `storage-volume`.
