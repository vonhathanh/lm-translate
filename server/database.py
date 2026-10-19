import os
from collections.abc import AsyncGenerator

from sqlalchemy import JSON, Column
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, Relationship, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


class Book(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None
    genres: list[str] | None = Field(default=None, sa_column=Column(JSON))
    chapters: list["Chapter"] = Relationship(back_populates="book")
    cover_image: str | None

    def __str__(self):
        return f"{self.id=}, {self.title=}"

    def __repr__(self):
        return f"{self.id=}, {self.title=}"


class Chapter(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    index: int
    title: str
    content: str
    raw: str | None
    book_id: int = Field(nullable=False, foreign_key="book.id")
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

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db_and_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session


async def add_chapter(chapter: Chapter):
    async with SessionLocal() as session, session.begin():
        session.add(chapter)
        await session.flush()
        return chapter


async def add_book(book: Book):
    async with SessionLocal() as session, session.begin():
        session.add(book)
        await session.flush()
        return book


async def find_book(title: str):
    async with SessionLocal() as session:
        statement = select(Book).where(Book.title == title)
        book = (await session.exec(statement)).first()
        return book


async def find_chapter(book_id: int, index: int):
    async with SessionLocal() as session:
        statement = select(Chapter).where(Chapter.book_id == book_id, Chapter.index == index)
        chapter = (await session.exec(statement)).first()
        return chapter
