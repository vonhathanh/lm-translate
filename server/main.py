from dotenv import load_dotenv  # noqa: I001
load_dotenv()

import asyncio
import bisect
import json
import logging
import math
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated

import redis.asyncio as redis
from bs4 import BeautifulSoup, NavigableString
from bullmq import Queue, Worker
from database import (
    Book,
    Chapter,
    add_book,
    add_chapters,
    create_db_and_tables,
    find_all_books,
    find_book,
    find_book_by_id,
    find_book_detail_by_id,
    find_chapter,
    find_chapter_detail_by_book_index,
    find_chapter_indices,
    update_chapter,
)
from dto import HtmlPageTranslationRequest, TranslateBookRequest
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from translation_service import llm_client
from worker import process

MAX_TOKENS_PER_BATCH = 500


logging.basicConfig(
    level=logging.INFO,  # Set minimum log level to capture
    format="%(asctime)s - %(levelname)s - %(message)s",  # Customize output format
    # filename='app.log',                           # Save logs to a file (omitting this prints to console)
    # filemode="w",  # 'w' overwrites file; 'a' appends (default)
)

logger = logging.getLogger(__name__)


REDIS_HOST = os.getenv("REDIS_HOST")
QUEUE_NAME = "fanqie-translation-queue"
NUM_WORKERS = 2
queue = Queue(QUEUE_NAME, {"connection": f"redis://{REDIS_HOST}:6379"})
workers = [Worker(QUEUE_NAME, process, {"connection": f"redis://{REDIS_HOST}:6379"}) for _ in range(NUM_WORKERS)]

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    # Startup: Initialize the Redis connection pool
    app.state.redis_pool = redis.ConnectionPool(
        host=REDIS_HOST,
        port=6379,
        db=0,
        decode_responses=True,  # Automatically converts bytes to strings
    )
    await queue.setGlobalRateLimit(1, 60000)  # 1 job per minute
    yield
    await app.state.redis_pool.disconnect()
    await queue.close()
    for worker in workers:
        await worker.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="./server/static"), name="static")
templates = Jinja2Templates(directory="./server/templates")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development; restrict in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency Injection provider to access Redis in routes
async def get_redis():
    # Yields a client session from the global connection pool
    client = redis.Redis(connection_pool=app.state.redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


RedisDep = Annotated[redis.Redis, Depends(get_redis)]


def create_batches(input_texts: set[str]) -> list[list[str]]:
    batches = []
    current_batch = []
    current_token_count = 0

    for text in input_texts:
        token_count = len(text.split())  # Simple token count based on words

        if current_token_count + token_count >= MAX_TOKENS_PER_BATCH:
            batches.append(current_batch)
            current_batch = []
            current_token_count = 0

        current_batch.append(text)
        current_token_count += token_count

    if current_batch:
        batches.append(current_batch)

    print(f"Created {len(batches)} batches from {len(input_texts)} unique input texts.")

    return batches


def parse_text_from_html(html: str) -> tuple[BeautifulSoup, set[str]]:
    """
    \d → digits (0-9)
    \W → non-word characters (special characters)
    _ → underscore (because _ is considered a word character in regex)
    + → one or more characters
    ^...$ → match the whole string

    This matches:
        only numbers → "12345"
        only special chars → "@#$%"
        mix of numbers + special chars → "123@#"

    This does NOT match:
        English letters → "abc"
        Vietnamese → "xin chào"
        Chinese → "你好"
        Japanese → "こんにちは"
    """
    PATTERN = r"^[\d\W_]+$"

    soup = BeautifulSoup(html, "html.parser")
    input_texts = set()
    for element in soup.find_all():
        if element.name in ["script", "style"]:
            continue
        direct_texts = [
            t.strip().lower()
            for t in element.contents
            if isinstance(t, NavigableString)
            and t.strip()
            and not bool(re.match(PATTERN, t.strip()))
        ]
        if direct_texts:
            input_texts.update(direct_texts)
    return soup, input_texts


def map_translated_text_to_html(
    soup: BeautifulSoup,
    input_batches: list[list[str]],
    translate_results: list[list[str]],
) -> str:
    translated_text = {}
    for i in range(len(translate_results)):
        for j in range(len(input_batches[i])):
            translated_text[input_batches[i][j]] = translate_results[i][j]

    for text_node in soup.find_all(string=True):
        normalized_text = text_node.strip().lower()

        if not normalized_text or normalized_text not in translated_text:
            continue

        translated = translated_text[normalized_text]
        # Replace text node
        text_node.replace_with(text_node.replace(text_node.text, translated))

    return str(soup)


@app.get("/")
def read_root():
    return "Hello World"


@app.get("/api/v1/books", response_class=HTMLResponse)
async def get_all_books(request: Request, page: int = 1, limit: int = 10) -> list[Book]:
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page must be > 0",
        )
    data = await find_all_books(page, limit)
    return templates.TemplateResponse(
        request=request,
        name="books.html",
        context={
            "books": data["books"],
            "total": data["total"],
            "page": page,
            "pages": math.ceil(data["total"] / limit),
        },
    )


@app.get("/api/v1/book/{book_id}", response_class=HTMLResponse)
async def get_book_detail(request: Request, book_id: int, page: int = 1, limit: int = 50):
    context = await find_book_detail_by_id(book_id)
    # TECH_DEBT
    # paginated manually, ideally chapters should be cached and user won't have to call this API again
    # but it's not supported for now
    # can use Redis to cache the content
    pages = math.ceil(len(context["chapters"]) / limit)
    context["chapters"] = context["chapters"][(page - 1) * limit : (page) * limit]
    return templates.TemplateResponse(
        request=request, name="book_detail.html", context={**context, "page": page, "pages": pages}
    )

@app.post("/api/v1/book/fanqie/raw")
async def insert_raw_fanqie_novel(
    r: RedisDep,
    file: UploadFile,
    start_index: Annotated[int | None, Form()] = None,
    end_index: Annotated[int | None, Form()] = None,
):
    start_index, end_index, filename, content = await validate_translate_fanqie_novel_input(
        file, start_index, end_index
    )

    book = await find_book(filename)
    if book is None:
        book = await add_book(Book(title=filename))
        logger.info(f"added new book, id: {book.id}, title: {filename}")

    try:
        chapter_index_regex = r"(第\d+章)"
        chapter_index: int = 0
        chapters = re.split(chapter_index_regex, content.decode("utf-8"))
        logger.info(f"Found ~={len(chapters) // 2} chapters in the file {filename}.")
        rows = []
        for i in range(1, len(chapters)):
            if re.match(chapter_index_regex, chapters[i]):
                chapter_index = int(chapters[i][1:-1])
                continue
            elif len(chapters[i]) < 20:
                continue
            if end_index >= chapter_index >= start_index:
                rows.append(Chapter(title=f"chapter_{chapter_index}", raw=chapters[i], index=chapter_index, book_id=book.id))
        await add_chapters(rows)
        await r.delete(f"book_{book.id}:index")
        return {"message": f"successfully inserted {len(rows)} chapters into the database"}
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode file. Please ensure it is UTF-8 encoded.",
        )

@app.post("/api/v1/translate/chapter/{chapter_id}")
async def translate_chapter(chapter_id: int):
    await queue.add(
        "translate_chapter",
        {
            "chapter_id": chapter_id,
        },
        {
            "attempts": 3,  # Total attempts, including the first try
            "backoff": {
                "type": "exponential",
                "delay": 1000,  # 1s, then 2s, then ...
            },
        },
    )
    await update_chapter(chapter_id, status="translating")
    return {"message": "translating, please wait"}

@app.post("/api/v1/translate/book/{book_id}")
async def translate_chapters(book_id: int, request: TranslateBookRequest, redis: RedisDep):
    book = await find_book_by_id(book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )
    chapter_indices = await get_chapter_indices(book_id, redis)
    for index in chapter_indices:
        if request.start_index <= index["index"] <= request.end_index:
            chapter = await find_chapter(book_id, index["index"])
            if chapter.status != "raw":
                logger.info(f"chapter {chapter.id} already translated or translating, skipping...")
                continue
            await queue.add(
                "translate_chapter",
                {
                    "chapter_id": chapter.id,
                },
                {
                    "attempts": 3,  # Total attempts, including the first try
                    "backoff": {
                        "type": "exponential",
                        "delay": 1000,  # 1s, then 2s, then ...
                    },
                },
            )
            await update_chapter(chapter.id, status="translating")
    return {"message": "translating, please wait"}


@app.get("/api/v1/chapter/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def get_chapter_detail(request: Request, book_id: int, chapter_index: int, r: RedisDep):
    context = await find_chapter_detail_by_book_index(book_id, chapter_index)
    content = context["chapter"].content or context["chapter"].raw

    chapter_indices = await get_chapter_indices(book_id, r)
    index = bisect.bisect_left(chapter_indices, chapter_index, key=lambda x: x["index"])

    prev, next = None, None
    if index > 0:
        prev = chapter_indices[index - 1]["index"]
    if index < len(chapter_indices) - 1:
        next = chapter_indices[index + 1]["index"]
    
    return templates.TemplateResponse(
        request=request,
        name="chapter.html",
        context={**context, "paragraphs": content.split("\n"), "prev_index": prev, "next_index": next},
    )


@app.post("/api/v1/translate/html")
async def translate_html_page(request: HtmlPageTranslationRequest):
    print(
        "Received translation request for model:",
        request.model,
        "and target language:",
        request.target_language,
    )
    # TODO: benchmark html parsers: lxlm, selectolax
    # parse html and extract text
    # normalize (trim, lowercase) then dedup the text to be translated
    # translate the text (without the html tags) then return a mapping from input text to translated text
    # map the translated text back to the original html structure using the input text
    # batch the translation requests to the translation API based on total token count (max 10000 tokens per batch)
    # support send multiple batches to different/same translation API endpoints in parallel
    soup, input_texts = parse_text_from_html(request.html)

    batches = create_batches(input_texts)

    start_time = time.time()

    tasks = [
        llm_client.batch_translate(request.model, request.target_language, batch)
        for batch in batches
    ]

    results = await asyncio.gather(*tasks)

    print(f"Total translation time: {time.time() - start_time:.2f} seconds")

    if not results or all(result is None for result in results):
        return {"translatedText": None}

    new_html = map_translated_text_to_html(soup, batches, results)

    return {"translatedText": new_html}


async def validate_translate_fanqie_novel_input(
    file: UploadFile,
    start_index: Annotated[int | None, Form()],
    end_index: Annotated[int | None, Form()],
):
    start_index = 0 if start_index is None else start_index
    end_index = 2**32 if end_index is None else end_index
    logger.info(f"{start_index=}, {end_index=}")
    # ensure it's a text file
    if not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .txt files are allowed.",
        )
    filename = file.filename.split(".txt")[0]

    content = await file.read()
    return start_index, end_index, filename, content


async def get_chapter_indices(book_id: int, r: RedisDep):
    redis_key = f"book_{book_id}:index"
    chapter_indices = await r.get(redis_key)
    if not chapter_indices:
        chapter_indices = await find_chapter_indices(book_id)
        if not chapter_indices:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Can't find chapter indices",
            )
        # convert sql model row into dict
        chapter_indices = [dict(row._mapping) for row in chapter_indices]
        await r.set(redis_key, json.dumps(chapter_indices))
    else:
        chapter_indices = json.loads(chapter_indices)
    # sample format: {'id': 296, 'index': 229, 'title': 'chapter_229'}
    return chapter_indices