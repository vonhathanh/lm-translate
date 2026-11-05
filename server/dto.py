from pydantic import BaseModel


class HtmlPageTranslationRequest(BaseModel):
    html: str
    model: str
    target_language: str


class TranslateBookRequest(BaseModel):
    start_index: int | None = 0
    end_index: int | None = 2**32


class TranslationOutput(BaseModel):
    items: list[str]


class UpdateBookRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    description: str | None = None
    genres: list[str] | None = None
    cover_image: str | None = None