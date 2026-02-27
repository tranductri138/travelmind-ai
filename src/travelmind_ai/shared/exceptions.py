from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class LLMError(AppError):
    def __init__(self, message: str = "LLM request failed") -> None:
        super().__init__(message, status_code=502)


class ScrapingError(AppError):
    def __init__(self, message: str = "Scraping failed") -> None:
        super().__init__(message, status_code=502)


class EmbeddingError(AppError):
    def __init__(self, message: str = "Embedding generation failed") -> None:
        super().__init__(message, status_code=502)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message},
        )
