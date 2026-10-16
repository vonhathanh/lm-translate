from dotenv import load_dotenv
load_dotenv() 

import asyncio
import re
import time

from typing import Annotated
from contextlib import asynccontextmanager
from requests import Session

from fastapi import Depends, FastAPI, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup, NavigableString
from bullmq import Queue, Worker

from dto import HtmlPageTranslationRequest
from model import create_db_and_tables, get_session
from translation_service import LLMClient


MAX_TOKENS_PER_BATCH = 500

SessionDep = Annotated[Session, Depends(get_session)]

async def process(job, job_token):
    print(
        f"Job id: {job.id}\n"
        f"Name: {job.name}\n"
        f"Data: {job.data}\n"
        f"Options: {job.opts}"
    )
    # job.data will include the data added to the queue
    return

QUEUE_NAME = 'fanqie-translation-queue'
queue = Queue(QUEUE_NAME, {"connection": "redis://localhost:6379"})
worker = Worker(QUEUE_NAME, process, {"connection": "redis://localhost:6379"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield
    await queue.close()
    await worker.close()


app = FastAPI(lifespan=lifespan)

llm_client = LLMClient()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development; restrict in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    PATTERN = r'^[\d\W_]+$'

    soup = BeautifulSoup(html, "html.parser")
    input_texts = set()
    for element in soup.find_all():
        if element.name in ["script", "style"]:
            continue
        direct_texts = [
            t.strip().lower()
            for t in element.contents
            if isinstance(t, NavigableString) and t.strip() and not bool(re.match(PATTERN, t.strip()))
        ]
        if direct_texts:
            input_texts.update(direct_texts)
    return soup, input_texts


def map_translated_text_to_html(soup: BeautifulSoup, input_batches: list[list[str]], translate_results: list[list[str]]) -> str:
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
        text_node.replace_with(
            text_node.replace(text_node.text, translated)
        )
    
    return str(soup)


@app.get("/")
def read_root():
    return "Hello World"


@app.post("/api/v1/translate-html")
async def translate_html_page(request: HtmlPageTranslationRequest):
    print("Received translation request for model:", request.model, "and target language:", request.target_language)
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

    tasks = [llm_client.batch_translate(request.model, request.target_language, batch) for batch in batches]

    results = await asyncio.gather(*tasks)

    print(f"Total translation time: {time.time() - start_time:.2f} seconds")
    
    if not results or all(result is None for result in results):
        return {"translatedText": None}

    new_html = map_translated_text_to_html(soup, batches, results)

    return {"translatedText": new_html}


@app.post("/api/v1/translate-text-from-file")
async def translate_html_page(file: UploadFile):
    # ensure it's a text file
    if not file.filename.endswith('.txt'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Only .txt files are allowed."
        )
    filename = file.filename.split('.txt')[0]

    content = await file.read()

    try:
        text_content = content.decode("utf-8")
        chapters = re.split(r"第\d+章", text_content)
        print('chapter 0: ', chapters[0])
        print('-'*40)
        print('chapter 1: ', chapters[1])
        print('-'*40)
        print('last chapter: ', chapters[-1])
        await queue.add("translate", {"id": 1})
        return {"message": f"translating {len(chapters)} chapters, please wait"}
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode file. Please ensure it is UTF-8 encoded."
        )
    # split txt into chapters & translate
    # save to db after translation
    # return number of chapters that are going to be translated