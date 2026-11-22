# User & Calculation Routes with Integration Testing

A FastAPI application backed by PostgreSQL. Users can register and log in with
hashed passwords and JWT tokens, and calculations can be saved and managed
through full **BREAD** routes (Browse, Read, Edit, Add, Delete). The project is
covered by unit, integration and end-to-end tests that run in GitHub Actions,
and every successful build on `main` publishes a scanned Docker image to
Docker Hub.

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
  - [Option A: run everything with Docker Compose](#option-a-run-everything-with-docker-compose)
  - [Option B: run the API locally](#option-b-run-the-api-locally)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Manual testing with /docs and /redoc](#manual-testing-with-docs-and-redoc)
- [Running the tests](#running-the-tests)
- [CI/CD pipeline](#cicd-pipeline)
- [Docker Hub image](#docker-hub-image)
- [Troubleshooting](#troubleshooting)

---

## Features

**Users**
- `POST /users/register` creates an account from the `UserCreate` schema. Passwords
  are stored only as **bcrypt** hashes, never in plain text.
- `POST /users/login` checks the password against the stored hash and returns a
  signed **JWT** access token. Either the username or the email can be used to log in.
- `GET /users/me` is protected: it needs `Authorization: Bearer <token>`.

**Calculations (BREAD)**

| Action | Method & path | Success |
|---|---|---|
| Browse | `GET /calculations` (optional `?user_id=`) | 200 |
| Read   | `GET /calculations/{id}` | 200 |
| Edit   | `PATCH /calculations/{id}` | 200 |
| Add    | `POST /calculations` | 201 |
| Delete | `DELETE /calculations/{id}` | 204 |

Supported types: `Add`, `Sub`, `Multiply`, `Divide` (any letter case is accepted).
The result is computed on the server with a polymorphic SQLAlchemy model
(single-table inheritance) and stored with the calculation.

**Validation and errors**
- Bad input returns **422** with Pydantic's error details (missing fields, non-numbers,
  unknown type, divide by zero, results too large to store).
- Unknown users or calculations return **404**, duplicate usernames or emails return
  **409**, and bad credentials return **401**. All of these are documented in OpenAPI.

---

## Tech stack

| Area | Tools |
|---|---|
| API | FastAPI, Uvicorn, Pydantic v2 |
| Database | PostgreSQL 17, SQLAlchemy 2.0, Alembic migrations |
| Security | bcrypt password hashing, PyJWT (HS256) |
| Tests | pytest, pytest-cov, FastAPI TestClient, Playwright |
| DevOps | Docker, Docker Compose, GitHub Actions, Trivy, Docker Hub |

---

## Project structure

```
.
├── app/
│   ├── main.py              # FastAPI app and all routes
│   ├── config.py            # Settings read from environment variables
│   ├── database.py          # Engine, session and get_db dependency
│   ├── auth/
│   │   ├── security.py      # bcrypt hash / verify
│   │   └── tokens.py        # JWT create / decode, get_current_user
│   ├── calculations/        # Calculation types and errors
│   ├── models/              # SQLAlchemy models (User, Calculation + subclasses)
│   ├── operations/          # Database operations for users and calculations
│   ├── schemas/             # Pydantic schemas (UserCreate, CalculationRead, ...)
│   └── templates/           # Calculator web page
├── alembic/                 # Database migrations
├── tests/
│   ├── unit/                # No database needed
│   ├── integration/         # Run against a real PostgreSQL database
│   └── e2e/                 # Playwright browser tests
├── .github/workflows/ci-cd.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt         # App + test dependencies
└── requirements-e2e.txt     # Adds Playwright for browser tests
```

---

## Getting started

### Prerequisites

- Python **3.12**
- Docker Desktop (for PostgreSQL, or for running the whole stack)
- Git

Clone the repository:

```bash
git clone https://github.com/av477/User-Calculation-Routes-Integration-Testing.git
```

```bash
cd User-Calculation-Routes-Integration-Testing
```

### Option A: run everything with Docker Compose

This starts PostgreSQL, applies the migrations, then starts the API.

```bash
docker compose up --build
```

Open:
- Calculator page: http://localhost:8000/
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Stop it with `Ctrl+C`, then remove the containers (add `-v` to also delete the database data):

```bash
docker compose down
```

If port 5432 or 8000 is already in use, pick other ports:

```bash
DB_PORT=5434 API_PORT=8001 docker compose up --build
```

### Option B: run the API locally

1. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   ```

   Windows (PowerShell):
   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   macOS / Linux:
   ```bash
   source .venv/bin/activate
   ```

2. **Install the dependencies** (use `python -m pip` so they go into this venv)

   ```bash
   python -m pip install -r requirements.txt
   ```

3. **Start only the database**

   ```bash
   docker compose up -d db
   ```

4. **Create your `.env` file** from the example and set a real secret:

   ```bash
   cp .env.example .env
   ```

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Paste the printed value into `JWT_SECRET_KEY` in `.env`.

5. **Apply the migrations**

   ```bash
   alembic upgrade head
   ```

6. **Start the server**

   ```bash
   uvicorn app.main:app --reload
   ```

   The API is now at http://127.0.0.1:8000.

---

## Configuration

Settings are read from environment variables or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | see `.env.example` | SQLAlchemy URL, e.g. `postgresql+psycopg2://appuser:apppassword@localhost:5432/secure_users` |
| `JWT_SECRET_KEY` | dev-only value | Key that signs login tokens. **Always set your own long random value outside development.** |
| `JWT_ALGORITHM` | `HS256` | Token signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | How long a login token is valid |

Inside Docker Compose the app reaches Postgres at host `db`. From your own
computer use `localhost`.

---

## API reference

### Users

| Method | Path | Body | Returns | Errors |
|---|---|---|---|---|
| POST | `/users/register` | `UserCreate` | `UserRead` (201) | 409 duplicate, 422 invalid |
| POST | `/users/login` | `UserLogin` | `Token` | 401 wrong credentials, 422 |
| GET | `/users/me` | — (Bearer token) | `UserRead` | 401 |
| GET | `/users/{user_id}` | — | `UserRead` | 404 |
| GET | `/users/{user_id}/calculations` | — | user with their calculations | 404 |

**Registration rules**
- `username`: 3–50 characters, letters, digits, `_`, `.`, `-` (stored in lowercase)
- `email`: a valid email address (stored in lowercase)
- `password`: at least 8 characters with an uppercase letter, a lowercase letter and a digit

Example:

```bash
curl -X POST http://localhost:8000/users/register -H "Content-Type: application/json" -d '{"username": "alice", "email": "alice@example.com", "password": "Secret123"}'
```

```bash
curl -X POST http://localhost:8000/users/login -H "Content-Type: application/json" -d '{"username": "alice", "password": "Secret123"}'
```

Login answer:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": { "id": "…", "username": "alice", "email": "alice@example.com", "created_at": "…" }
}
```

```bash
curl http://localhost:8000/users/me -H "Authorization: Bearer <access_token>"
```

### Calculations

| Method | Path | Body | Returns | Errors |
|---|---|---|---|---|
| GET | `/calculations` | — (`?user_id=` optional) | list of `CalculationRead` | 422 bad user_id |
| GET | `/calculations/{id}` | — | `CalculationRead` | 404, 422 |
| PATCH | `/calculations/{id}` | `{"a": …}`, `{"b": …}` or both | `CalculationRead` | 404, 422 |
| POST | `/calculations` | `CalculationCreate` | `CalculationRead` (201) | 404 unknown user, 422 |
| DELETE | `/calculations/{id}` | — | empty (204) | 404, 422 |
| POST | `/calculate` | `{"a", "b", "type"}` | result only, nothing saved | 422 |

Example:

```bash
curl -X POST http://localhost:8000/calculations -H "Content-Type: application/json" -d '{"a": 10, "b": 4, "type": "Sub", "user_id": "<user id>"}'
```

```json
{ "id": "…", "a": 10.0, "b": 4.0, "type": "Sub", "result": 6.0, "user_id": "…", "created_at": "…", "updated_at": "…" }
```

Editing recomputes the result with the same operation (the type can't change):

```bash
curl -X PATCH http://localhost:8000/calculations/<id> -H "Content-Type: application/json" -d '{"b": 10}'
```

Error answers look like:

```json
{ "detail": "Calculation not found" }
```

---

## Manual testing with /docs and /redoc

1. Start the app (Option A or B above).
2. Open **http://localhost:8000/docs** (Swagger UI).
3. **Register:** expand `POST /users/register` → *Try it out* → send a username, email
   and password → expect **201** and a user without any password field.
4. **Login:** `POST /users/login` with the same details → expect **200** and an
   `access_token`. A wrong password should give **401**.
5. **Authorize:** click **Authorize** (top right), paste the `access_token`, then call
   `GET /users/me` → expect **200** with your user. Without the token → **401**.
6. **Add:** `POST /calculations` with `a`, `b`, `type` and your user `id` → **201** with the result.
7. **Browse / Read:** `GET /calculations` and `GET /calculations/{id}` → **200**.
8. **Edit:** `PATCH /calculations/{id}` with a new `b` → **200** with a new result.
9. **Delete:** `DELETE /calculations/{id}` → **204**, then reading it again → **404**.
10. **Invalid data:** try `"type": "Power"`, `"a": "abc"` or `Divide` with `b = 0` → **422**.

**http://localhost:8000/redoc** shows the same API as read-only documentation, including
the request and response schemas and the documented 401/404/409 errors.

---

## Running the tests

The tests are grouped with pytest markers:

| Marker | Folder | Needs |
|---|---|---|
| `unit` | `tests/unit` | nothing |
| `integration` | `tests/integration` | a running PostgreSQL database |
| `e2e` | `tests/e2e` | PostgreSQL + Playwright Chromium |

> **Warning:** the integration and e2e tests drop and recreate the tables in the
> database named by `DATABASE_URL`. Never point them at a database with data you want to keep.

**Unit tests**

```bash
pytest tests/unit -m unit
```

**Integration tests** (start the database first with `docker compose up -d db`)

```bash
pytest tests/integration -m integration --cov=app --cov-report=term-missing
```

What they cover:
- **Users:** register, login, `/users/me`, duplicate and invalid registrations, wrong
  passwords, and checks with raw SQL that the row and its bcrypt hash are really stored.
- **Calculations:** create → retrieve → update → delete, checked in the database after each
  step, for every type.
- **Invalid data:** status codes (404, 422) and error bodies, and that nothing was saved.
- **Migrations:** `alembic upgrade head` builds a schema that matches the models.

**End-to-end browser tests**

```bash
python -m pip install -r requirements-e2e.txt
```

```bash
playwright install chromium
```

```bash
pytest tests/e2e -m e2e
```

**Everything with the same coverage gate as CI**

```bash
pytest tests/unit tests/integration --cov=app --cov-fail-under=90
```

---

## CI/CD pipeline

Defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml). It runs on
**every push to any branch** and on pull requests to `main`.

**Job 1: Test**
1. Starts a **PostgreSQL 17** service container.
2. Installs the dependencies.
3. Runs `alembic upgrade head` and `alembic check` (migrations must match the models).
4. Runs the unit tests, then the integration tests with a **90 % coverage** minimum.
5. Installs Chromium and runs the Playwright end-to-end tests.
6. Uploads the JUnit results and `coverage.xml` as a build artifact.

**Job 2: Build, scan and deploy** (only if the tests pass)
1. Builds the Docker image.
2. Scans it with **Trivy**. The build fails on any fixable **HIGH** or **CRITICAL** vulnerability.
3. On a push to `main` only: logs in to Docker Hub and pushes the image tagged with the
   commit SHA and `latest`.

### Required repository secrets

In GitHub go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | your Docker Hub username |
| `DOCKERHUB_TOKEN` | a Docker Hub access token (Docker Hub → Account settings → Personal access tokens) |

---

## Docker Hub image

After a successful run on `main`, the image is available as:

```
<your-dockerhub-username>/601_module_12-user_calculation:latest
```

Docker Hub page: `https://hub.docker.com/r/<your-dockerhub-username>/601_module_12-user_calculation`

Run it against your own PostgreSQL database:

```bash
docker run -p 8000:8000 -e DATABASE_URL=postgresql+psycopg2://appuser:apppassword@host.docker.internal:5432/secure_users -e JWT_SECRET_KEY=<your-secret> <your-dockerhub-username>/601_module_12-user_calculation:latest
```

The container applies the migrations on start, then serves the API on port 8000.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `connection refused` on port 5432 | Start the database: `docker compose up -d db`, and check that `DATABASE_URL` uses `localhost` outside Docker. |
| Port 5432 or 8000 already in use | Use `DB_PORT=5434` / `API_PORT=8001` with Docker Compose and update `DATABASE_URL`. |
| `ModuleNotFoundError` after installing | You probably installed into another environment. Activate `.venv` and use `python -m pip install -r requirements.txt`. |
| `relation "users" does not exist` | Run `alembic upgrade head`. |
| `401 Invalid or expired token` | Log in again. Tokens last `ACCESS_TOKEN_EXPIRE_MINUTES`, and tokens signed with a different `JWT_SECRET_KEY` are rejected. |
| Trivy step fails in CI | Read the table in the job log and upgrade the listed package to its *Fixed Version* in `requirements.txt`. |
| Docker Hub push step fails | Check that the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets are set. |
