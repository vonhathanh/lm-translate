from pydantic import BaseModel


class HtmlPageTranslationRequest(BaseModel):
    html: str
    model: str
    target_language: str


class TranslationOutput(BaseModel):
    items: list[str]