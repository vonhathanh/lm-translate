from pydantic import BaseModel


class Item(BaseModel):
    text: str
    model: str
    language: str