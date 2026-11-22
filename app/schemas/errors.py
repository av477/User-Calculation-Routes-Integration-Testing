"""Shape of the error answers raised with HTTPException, for the OpenAPI docs."""

from typing import Any

from pydantic import BaseModel


class ErrorMessage(BaseModel):
    """Body of a 401, 404 or 409 answer, e.g. ``{"detail": "User not found"}``."""

    detail: str


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Build a route's ``responses=`` entry so /docs lists these error codes."""
    descriptions = {
        401: "Missing, invalid or expired credentials",
        404: "Not found",
        409: "Conflict with existing data",
    }
    return {code: {"model": ErrorMessage, "description": descriptions[code]} for code in codes}
