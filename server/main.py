import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup, NavigableString
from google import genai
from google.genai import types

from dotenv import load_dotenv

from dto import HtmlPageTranslationRequest, TranslationOutput

load_dotenv() 


MAX_TOKENS_PER_BATCH = 2000


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
    prompt = "Translate the following array of text to {}, return an array of translated text preserving input order. input array: {}".format(target_language, batch)
    print(f"prompt: {prompt}")
    response = client.models.generate_content(
        model=model, 
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TranslationOutput,
        ),
    )
    parsed: TranslationOutput = response.parsed
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

    return batches

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/api/v1/translate/html")
async def translate_html_page(request: HtmlPageTranslationRequest):
    # TODO: benchmark html parsers: lxlm, selectolax
    # parse html and extract text
    # normalize (trim, lowercase) then dedup the text to be translated
    # translate the text (without the html tags) then return a mapping from input text to translated text
    # map the translated text back to the original html structure using the input text
    # batch the translation requests to the translation API based on total token count (max 10000 tokens per batch)
    # support send multiple batches to different/same translation API endpoints in parallel
    soup = BeautifulSoup(request.html, "html.parser")
    input_texts = set()
    for element in soup.find_all():
        direct_texts = [
            t.strip().lower()
            for t in element.contents
            if isinstance(t, NavigableString) and t.strip()
        ]
        if direct_texts:
            input_texts.update(direct_texts)
    print(f"input_texts: {input_texts}")

    batches = create_batches(input_texts)

    print(f"created {len(batches)} batches")

    tasks = [translate(request.model, request.target_language, batch) for batch in batches]

    results = await asyncio.gather(*tasks)
    
    for res in results:
        print(f"translation result: {res}")

    translated_text = {}
    for i, result in enumerate(results):
        for j in range(len(batches[i])):
            translated_text[batches[i][j]] = result[j]

    print(f"translated_text: {translated_text}")

    for text_node in soup.find_all(string=True):
        normalized_text = text_node.strip().lower()

        if not normalized_text:
            continue

        print(f"processing text node: '{normalized_text}'")

        if normalized_text in translated_text:
            translated = translated_text[normalized_text]

            # Replace text node
            text_node.replace_with(
                text_node.replace(text_node.text, translated)
            )

    new_html = str(soup)

    return {"translatedText": new_html}