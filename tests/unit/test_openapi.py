"""The OpenAPI document (/openapi.json, shown at /docs and /redoc) describes
every route's input, output and error answers correctly. No database needed."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def spec():
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def schema_name(schema):
    if schema is None:
        return None
    if schema.get("type") == "array":
        return "list[" + schema["items"]["$ref"].rsplit("/", 1)[-1] + "]"
    return schema["$ref"].rsplit("/", 1)[-1]


def json_schema(part):
    return part.get("content", {}).get("application/json", {}).get("schema")


# (method, path, request body schema, success code, response schema, documented errors)
ROUTES = [
    ("post", "/calculations", "CalculationCreate", "201", "CalculationRead", {"404", "422"}),
    ("get", "/calculations", None, "200", "list[CalculationRead]", {"422"}),
    ("get", "/calculations/{calculation_id}", None, "200", "CalculationRead", {"404", "422"}),
    ("patch", "/calculations/{calculation_id}", "CalculationUpdate", "200", "CalculationRead",
     {"404", "422"}),
    ("delete", "/calculations/{calculation_id}", None, "204", None, {"404", "422"}),
    ("post", "/users/register", "UserCreate", "201", "UserRead", {"409", "422"}),
    ("post", "/users/login", "UserLogin", "200", "Token", {"401", "422"}),
    ("get", "/users/me", None, "200", "UserRead", {"401"}),
    ("get", "/users/{user_id}", None, "200", "UserRead", {"404", "422"}),
    ("get", "/users/{user_id}/calculations", None, "200", "UserCalculations", {"404", "422"}),
]


@pytest.mark.parametrize(("method", "path", "request_body", "code", "response", "errors"), ROUTES)
def test_route_is_documented(spec, method, path, request_body, code, response, errors):
    operation = spec["paths"][path][method]

    body = operation.get("requestBody")
    assert schema_name(json_schema(body) if body else None) == request_body
    assert schema_name(json_schema(operation["responses"][code])) == response
    assert set(operation["responses"]) - {code} == errors
    for error in errors - {"422"}:
        assert schema_name(json_schema(operation["responses"][error])) == "ErrorMessage"


def test_only_users_me_requires_a_token(spec):
    assert spec["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    secured = [
        (method, path)
        for path, operations in spec["paths"].items()
        for method, operation in operations.items()
        if operation.get("security")
    ]
    assert secured == [("get", "/users/me")]


def test_no_response_schema_exposes_a_password(spec):
    schemas = spec["components"]["schemas"]
    for name in ("UserRead", "Token", "UserCalculations"):
        assert not any("password" in prop for prop in schemas[name]["properties"])


@pytest.mark.parametrize("page", ["/docs", "/redoc"])
def test_docs_pages_are_served(page):
    response = TestClient(app).get(page)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
