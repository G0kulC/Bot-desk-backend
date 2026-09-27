from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class OkOut(BaseModel):
    ok: bool = True


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody
