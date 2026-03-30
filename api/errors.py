from fastapi import Request
from fastapi.responses import JSONResponse
from catalog.manager import SchemaEvolutionError


def _error(code: str, message: str, status: int, details: dict = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    return _error("NOT_FOUND", str(exc).strip("'"), 404)


async def schema_evolution_handler(request: Request, exc: SchemaEvolutionError) -> JSONResponse:
    return _error("SCHEMA_EVOLUTION_ERROR", str(exc), 422)


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return _error("VALIDATION_ERROR", str(exc), 422)


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error("INTERNAL_ERROR", "An unexpected error occurred.", 500)
