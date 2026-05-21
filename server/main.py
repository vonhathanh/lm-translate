import asyncio
import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup, NavigableString
from google import genai
from google.genai import types

from dotenv import load_dotenv

from dto import HtmlPageTranslationRequest, TranslationOutput
from translation_service import TRANSLATION_PROMPT

load_dotenv() 


MAX_TOKENS_PER_BATCH = 500


app = FastAPI()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# Define the origins that are allowed to make requests
origins = [
    "http://localhost:5000",  # Common for React
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development; restrict in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def translate(model: str, target_language: str, batch: list[str]):
    prompt = TRANSLATION_PROMPT.format(target_language, batch)
    response = client.models.generate_content(
        model=model, 
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TranslationOutput,
        ),
    )
    parsed: TranslationOutput = response.parsed
    print(f"Translated batch: {parsed.items}, len: {len(parsed.items)}, input batch len: {len(batch)}")
    return parsed.items


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
    print(f"{input_texts=}, total unique text nodes to translate: {len(input_texts)}")
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
    return {"Hello": "World"}


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

    tasks = [translate(request.model, request.target_language, batch) for batch in batches]

    results = await asyncio.gather(*tasks)

    new_html = map_translated_text_to_html(soup, batches, results)

    print(f"input html: {request.html[:500]}...")
    print(f"translated html: {new_html[:500]}...")

    return {"translatedText": new_html}