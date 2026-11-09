from dotenv import load_dotenv

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
from bullmq import Queue, Worker
from database import (
    Book,
    Chapter,
    ChapterStatus,
    add_book,
    add_chapters,
    create_db_and_tables,
    find_all_books,
    find_book,
    find_book_by_id,
    find_book_detail_by_id,
    find_chapter,
    find_chapter_by_id,
    find_chapter_detail_by_book_index,
    find_chapter_indices,
    update_book,
    update_chapter,
)
from dto import (
    HtmlPageTranslationRequest,
    TranslateBookRequest,
    TranslateRequest,
    UpdateBookRequest,
    UpdateChapterRequest,
)
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from translation_service import (
    create_batches,
    llm_client,
    map_translated_text_to_html,
    parse_text_from_html,
)
from worker import process

logging.basicConfig(
    level=logging.INFO,  # Set minimum log level to capture
    format="%(asctime)s - %(levelname)s - %(message)s",  # Customize output format
    # filename='app.log',                           # Save logs to a file (omitting this prints to console)
    # filemode="w",  # 'w' overwrites file; 'a' appends (default)
)

logger = logging.getLogger(__name__)


REDIS_HOST = os.getenv("REDIS_HOST")
QUEUE_NAME = "fanqie-translation-queue"
queue = Queue(QUEUE_NAME, {"connection": f"redis://{REDIS_HOST}:6379"})
worker = Worker(QUEUE_NAME, process, {"connection": f"redis://{REDIS_HOST}:6379", "autorun": False})


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
    asyncio.ensure_future(worker.run())
    yield
    await app.state.redis_pool.disconnect()
    await queue.close()
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
                next_chapter_index = int(chapters[i][1:-1])
                if next_chapter_index <= chapter_index:
                    chapter_index += 1
                else:
                    chapter_index = next_chapter_index
                continue
            elif len(chapters[i]) < 20:
                continue
            if end_index >= chapter_index >= start_index:
                rows.append(
                    Chapter(
                        title=f"chapter_{chapter_index}",
                        raw=chapters[i],
                        index=chapter_index,
                        book_id=book.id,
                    )
                )
        await add_chapters(rows)
        await r.delete(f"book_{book.id}:index")
        return {"message": f"successfully inserted {len(rows)} chapters into the database"}
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode file. Please ensure it is UTF-8 encoded.",
        )


@app.patch("/api/v1/book/{book_id}")
async def update_book_details(book_id: int, book: UpdateBookRequest):
    existing_book = await find_book_by_id(book_id)
    if not existing_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )
    await update_book(book_id, **book.model_dump(exclude_unset=True))
    return {"message": "Book updated successfully"}


@app.post("/api/v1/translate/chapter/{chapter_id}")
async def translate_chapter(chapter_id: int):
    chapter = await find_chapter_by_id(chapter_id)
    if not chapter:
        logger.error(f"chapter with id={chapter_id} not found, skipping this job!")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"chapter with id={chapter_id} not found, skipping!",
        )
    translated_result = await llm_client.translate_single_chapter(
        chapter.raw, os.getenv("LLM_MODEL", "deepseek-flash")
    )
    if translated_result:
        chapter = await update_chapter(
            chapter.id,
            title=translated_result.title,
            content=translated_result.content,
            status=ChapterStatus.translated,
        )
        return {
            "message": "OK",
            "chapter_id": chapter_id,
            "title": translated_result.title,
            "content": translated_result.content,
        }
    else:
        logger.error(
            f"translation failed for chapter id: {chapter.id}, result: {translated_result}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"translation failed for chapter id: {chapter.id}, result: {translated_result}",
        )

    


@app.post("/api/v1/translate/hachimi")
async def translate_text(body: TranslateRequest):
    return await llm_client.hachimi_translate(body.text)


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
        context={
            **context,
            "paragraphs": content.split("\n"),
            "prev_index": prev,
            "next_index": next,
        },
    )


@app.patch("/api/v1/chapter/{chapter_id}")
async def update_chapter_details(chapter_id: int, chapter: UpdateChapterRequest):
    existing_chapter = await find_chapter_by_id(chapter_id)
    if not existing_chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )
    await update_chapter(chapter_id, **chapter.model_dump(exclude_unset=True))
    return {"message": "Chapter updated successfully"}


@app.get("/api/v1/status/chapter/{chapter_id}")
async def get_chapter_status(chapter_id: int):
    chapter = await find_chapter_by_id(chapter_id)
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )
    return {"status": chapter.status}


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
