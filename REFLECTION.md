# Reflection: User & Calculation Routes with Integration Testing

## Module 12 reflection

Module 12 connected the pieces I built in Modules 10 and 11 into a working API. My existing User and Calculation SQLAlchemy models needed almost no changes: the registration route passes a validated `UserCreate` to my `create_user` function, and the calculation routes reuse the polymorphic `Calculation.create` factory, so Add, Sub, Multiply and Divide each compute their own result. Because my Pydantic schemas already defined valid input, they translated directly into route-level behaviour. FastAPI rejects bad data with a 422 before any database code runs, and `CalculationRead` and `UserRead` control exactly what each response contains.

Integration testing with `pytest` showed me these endpoints stay reliable. My tests call every route through FastAPI's `TestClient`, then read the PostgreSQL tables back with plain SQL to confirm that rows are really created, updated and deleted, and that invalid requests store nothing. Docker Compose runs the same PostgreSQL 17 database locally that GitHub Actions starts as a service, so a passing test means the same thing on my laptop and in CI.

For security, passwords are stored only as bcrypt hashes and verified with a hash check at login, which then issues a signed JWT that expires after 30 minutes. `/users/me` rejects missing or invalid tokens with a 401, and no response ever includes a password hash. The main gap I found is ownership: the calculation routes don't yet check that the logged-in user owns a calculation, so requiring a token there and comparing user IDs is my next improvement.

---

# Development notes

## What I learned

This assignment turned a calculation model into a complete, tested web API. I learned how
to build **user registration and login** in FastAPI: storing only bcrypt password hashes,
checking a password against its hash at login, and issuing a signed **JWT** that protects
routes such as `/users/me`. I also implemented full **BREAD** routes for calculations and
saw how Pydantic schemas (`CalculationCreate`, `CalculationRead`) define exactly what goes
in and comes out of the API. FastAPI then documents everything automatically in `/docs`
and `/redoc`.

On the testing side, I learned that **integration tests are most convincing when they check
the database directly**. After each API call my tests read the rows back with plain SQL, to
confirm that a user was stored with a hashed password, that a calculation was created,
updated and deleted, and that invalid requests returned the right status code and error
message without saving anything. Running these tests against a real PostgreSQL service in
GitHub Actions showed me how CI catches problems before they reach production.

## A challenge I resolved

The hardest problem appeared after every test was already passing. The CI pipeline still
failed, and no Docker image was pushed to Docker Hub. The failing step was the **Trivy
security scan**: the version of PyJWT I had added for login tokens (2.10.1) had six known
vulnerabilities, one of them a **critical authentication bypass**. Because the pipeline
blocks any image with fixable HIGH or CRITICAL issues, the deployment stopped.

To resolve it, I read Trivy's report to find which package and versions were affected,
upgraded PyJWT to a patched release (2.15.1), and reran the unit and integration tests to
make sure the token code still worked. I also confirmed that the vulnerability database
lists no known issues for the new version.

This taught me that **passing tests don't mean an application is safe to release**.
Dependencies, especially security libraries, need to be scanned and kept up to date, and
having that check built into the CI/CD pipeline is what stopped a vulnerable image from
being published.
