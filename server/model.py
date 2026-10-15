import os
from collections.abc import AsyncGenerator

from sqlalchemy import Column, JSON
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, Relationship, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class Book(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None
    genres: list[str] | None = Field(default=None, sa_column=Column(JSON))
    chapters: list["Chapter"] = Relationship(back_populates="book")
    cover_image: str | None


class Chapter(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    content: str
    book_id: int | None = Field(default=None, foreign_key="book.id")
    book: Book | None = Relationship(back_populates="chapters")


engine = create_async_engine(
    URL.create(
        drivername="postgresql+asyncpg",
        username=os.getenv("PG_USERNAME"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=5432,
        database=os.getenv("PG_DATABASE"),
    )
)


async def create_db_and_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session
