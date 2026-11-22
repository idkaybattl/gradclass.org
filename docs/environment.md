# Environment variables

`gradclassorg/settings.py` reads its configuration from environment variables
and loads a `.env` file from the repo root with `load_dotenv()` at import time.
`.env` is gitignored; `.env.example` is the committed template for the mail keys.

Only `SECRET_KEY` is required in every setup. Everything else has a default that
works for dev; the production rows below say what must be set there.

## Server

| Variable | Required | Default | What it does |
|---|:--:|---|---|
| `SECRET_KEY` | **yes** | — | Django signing key. No default; generate one per environment and keep it secret. |
| `ENV` | optional | `dev` | `dev` uses the local SQLite file `db.sqlite3`. Any other value (e.g. `prod`) switches to Postgres. |
| `DEBUG` | optional | off | Only the exact string `True` enables Django debug mode. Anything else turns it off. |

## Database (only used when `ENV` is not `dev`)

| Variable | Required | Default | What it does |
|---|:--:|---|---|
| `POSTGRES_DB` | **yes** in production | — | Postgres database name. |
| `POSTGRES_USER` | **yes** in production | — | Postgres user. |
| `POSTGRES_PASSWORD` | **yes** in production | — | Postgres password. |
| `DB_HOST` | optional | `db` | Postgres host. The port is fixed at `5432` in settings. |

## Hosts and security

| Variable | Required | Default | What it does |
|---|:--:|---|---|
| `ALLOWED_HOSTS` | optional | `*` | Comma-separated hosts Django serves. Set the real domain in production. |
| `CSRF_TRUSTED_ORIGINS` | optional | `*` | Comma-separated origins **with scheme**, e.g. `https://gradclass.org`. Set the real site in production. |

`SECURE_PROXY_SSL_HEADER` is set in `settings.py` so Django trusts
`X-Forwarded-Proto: https` from the TLS-terminating proxy. The proxy must send
that header; otherwise `request.is_secure()` stays false and reset links are
built as `http://`.

## Contact page

| Variable | Required | Default | What it does |
|---|:--:|---|---|
| `CONTACT_USER_ID` | optional | empty | ID of the user whose profile supplies the contact page details. Empty uses the first active superuser. |

## Email

All mail keys are optional. With `EMAIL_HOST` empty, dev uses Django's console
backend and mails are printed to the terminal instead of being sent. Settings
already fall back to the defaults when a key exists but is empty.

| Variable | Required | Default | What it does |
|---|:--:|---|---|
| `EMAIL_HOST` | optional | empty | SMTP server. Empty means console backend. |
| `EMAIL_HOST_USER` | optional | empty | SMTP user. |
| `EMAIL_HOST_PASSWORD` | optional | empty | SMTP password. Never commit it. |
| `EMAIL_PORT` | optional | `587` | SMTP port. |
| `EMAIL_USE_TLS` | optional | on | STARTTLS. Accepts `1`/`true`/`yes`/`on`. Ignored when SSL is on. |
| `EMAIL_USE_SSL` | optional | off | Implicit SSL. Accepts `1`/`true`/`yes`/`on`; forces `EMAIL_USE_TLS` off, so both can never be on. |
| `EMAIL_BACKEND` | optional | derived | Overrides the backend entirely. Otherwise SMTP when `EMAIL_HOST` is set, console when not. |
| `DEFAULT_FROM_EMAIL` | optional | `noreply@gradclass.org` | `From` address for all mail; also used as `SERVER_EMAIL`. |
| `DEFAULT_REPLY_TO` | optional | `moritz.fechte@gmail.com` | `Reply-To` for password reset mails, so replies reach a monitored inbox. |

`EMAIL_TIMEOUT` is fixed at 10 seconds and `PASSWORD_RESET_TIMEOUT` at one day in
settings; neither is configurable from env.
