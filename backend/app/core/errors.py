from typing import NoReturn

from fastapi import HTTPException


def fail(code: str, status: int = 409) -> NoReturn:
    raise HTTPException(status, detail={"code": code})
