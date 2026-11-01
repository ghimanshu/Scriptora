from typing import NoReturn

from fastapi import HTTPException


def fail(code: str, status: int = 409, *, details: dict | None = None) -> NoReturn:
    detail: dict = {"code": code}
    if details is not None:
        detail["details"] = details
    raise HTTPException(status, detail=detail)
