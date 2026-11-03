import logging
import os

from database import (
    Book,
    Chapter,
    ChapterStatus,
    add_book,
    add_chapter,
    find_book,
    find_chapter,
    find_chapter_by_id,
    update_chapter,
)
from translation_service import llm_client

logger = logging.getLogger(__name__)


async def process(job, job_token):
    logger.info(f"Job id: {job.id}, Name: {job.name}")
    try:
        if job.name == "translate":
            await translate_new_chapter(job)
        elif job.name == "translate_chapter":
            await translate_current_chapter(job)
        else:
            raise ValueError("invalid job name")
    except Exception as e:
        logger.error(f"Job id {job.id} failed, error message: {e}")


async def translate_current_chapter(job):
    chapter_id = job.data["chapter_id"]
    chapter = await find_chapter_by_id(chapter_id)
    if not chapter:
        logger.error(f"chapter with id={chapter_id} not found, skipping this job!")
        return
    translated_result = await llm_client.translate_single_chapter(
        chapter.raw, os.getenv("LLM_MODEL", "deepseek-flash")
    )
    if translated_result:
        chapter = await update_chapter(
            chapter.id,
            title=translated_result.title,
            content=translated_result.content,
            status=ChapterStatus.translated
        )
        logger.info(f"translated chapter id: {chapter_id}, title: {translated_result.title}")
    else:
        logger.error(f"translation failed for chapter id: {chapter.id}, result: {translated_result}")
    

async def translate_new_chapter(job):
    book_title = job.data["book_title"]
    chapter_index = job.data["chapter_index"]
    
    book = await find_book(book_title)
    if book is None:
        book = await add_book(Book(title=book_title))
        logger.info(f"added new book, id: {book.id}")
    
    logger.info(f"found book, id= {book.id}")
    
    chapter = await find_chapter(book.id, chapter_index)
    if chapter:
        logger.info(
            f"chapter for book: {book_title}, index: {chapter_index} already existed at chapter_id = {chapter.id}, skipping this job!"
        )
        return
    logger.info(f"chapter with index={chapter_index} not found, translating...")
    
    translated_result = await llm_client.translate_single_chapter(
        job.data["content"], os.getenv("LLM_MODEL", "deepseek-flash")
    )
    if translated_result:
        chapter = await add_chapter(
            Chapter(
                title=translated_result.title,
                content=translated_result.content,
                raw=job.data["content"],
                book_id=book.id,
                index=chapter_index,
            ),
        )
        logger.info(f"added new chapter, index: {chapter.index}, title: {chapter.title}")
    else:
        logger.error(f"translation failed for book: {book_title}, chapter index: {chapter_index}, result: {translated_result}")