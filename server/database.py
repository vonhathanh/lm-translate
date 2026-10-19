import os
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, Relationship, SQLModel, func, select, update
from sqlmodel.ext.asyncio.session import AsyncSession


class Base(SQLModel, table=False):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=func.now)
    updated_at: datetime = Field(default_factory=func.now, sa_column_kwargs={"onupdate": func.now()})


class Book(Base, table=True):
    title: str
    author: str | None = Field(default="AI")
    description: str | None
    genres: list[str] | None = Field(default=None, sa_column=Column(JSON))
    chapters: list["Chapter"] = Relationship(back_populates="book")
    cover_image: str | None
    chapter_count: int = Field(default=0, nullable=False)

    def __str__(self):
        return f"{self.id=}, {self.title=}"

    def __repr__(self):
        return f"{self.id=}, {self.title=}"


class Chapter(Base, table=True):
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


async def add_chapter(chapter: Chapter, chapter_count: int):
    async with SessionLocal() as session, session.begin():
        session.add(chapter)
        statement = update(Book).where(Book.id == chapter.book_id).values(chapter_count=chapter_count + 1)
        await session.exec(statement)
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
        return (await session.exec(statement)).first()

async def find_all_books(page: int, limit: int):
    async with SessionLocal() as session:
        statement = select(Book).order_by(Book.id).offset(page * limit).limit(limit)
        return (await session.exec(statement)).fetchmany()

async def find_chapter(book_id: int, index: int):
    async with SessionLocal() as session:
        statement = select(Chapter).where(Chapter.book_id == book_id, Chapter.index == index)
        return (await session.exec(statement)).first()
