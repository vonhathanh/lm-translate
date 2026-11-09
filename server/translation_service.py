import json
import logging
import os
import random
import re

from bs4 import BeautifulSoup, NavigableString
from google import genai
from google.genai import Client, types
from hachimi.hardware import detect_hardware_profile
from hachimi.translator import DEFAULT_MODEL_KEY, Backend, HachimiTranslator
from openai import AsyncOpenAI
from prompts import TRANSLATE_BOOK_PROMPT, TRANSLATE_HTML_PROMPT
from pydantic import BaseModel

logger = logging.getLogger(__name__)

GOOGLE_LLM_OPTIONS = {
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
}

DEEPSEEK_LLM_OPTIONS = {
    "deepseek-flash",
    "deepseek-v4-pro",
}

OPENAI_LLM_OPTIONS = {
    "gpt-6-astra",  # the best
    "gpt-6.1-sol",  # acceptable
    "gpt-6-luna",  # the cheapest and the worst
}

# not supported yet, too lazy, sorry bro
MUSE_SPARK_LLM_OPTIONS = {
    "muse-spark-1.3-contributor",  # too fucking cheap to be true
    "muse-spark-1.3",  # same as above expect won't use our code to train AI
}

LOCAL_LLM_OPTIONS = {
    "localhost",  # local LLM server
    "HachimiMT-60-QT",  # local LLM server
}

MAX_TOKENS_PER_BATCH = 500


class ChapterTranslationResult(BaseModel):
    title: str
    content: str


class LLMClient:
    def __init__(self):
        self.gemini_client: Client = None
        self.deepseek_client: AsyncOpenAI = None
        self.local_llm_client: AsyncOpenAI = None
        self.openai_client: AsyncOpenAI = None
        self.hachimi_translator = HachimiTranslator(detect_hardware_profile()         )
        self.hachimi_translator.load(DEFAULT_MODEL_KEY, Backend.CT2)

    async def call_google_llm(
        self, model: str, prompt: str, output_schema: type[BaseModel] | None = None
    ):
        if self.gemini_client is None:
            self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = await self.gemini_client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=output_schema,
            ),
        )
        return response.parsed

    async def call_deepseek_llm(
        self, model: str, prompt: str, output_schema: type[BaseModel] | None = None
    ):
        if self.deepseek_client is None:
            self.deepseek_client = AsyncOpenAI(
                api_key=os.environ.get("DEEP_SEEK_API_KEY"),
                base_url="https://api.deepseek.com",
            )
        response = await self.deepseek_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            reasoning_effort="minimal",
        )
        logger.info(f"LLM usage: {response.usage}")

        result = loads(response.choices[0].message.content)
        if output_schema:
            return output_schema.model_validate(result)
        return result

    async def call_local_llm(self, model: str, prompt: str):
        if self.local_llm_client is None:
            self.local_llm_client = AsyncOpenAI(
                api_key=os.getenv("LOCAL_LLM_API_KEY"),
                base_url=os.getenv("LOCAL_LLM_API_URL"),
            )
        response = await self.local_llm_client.chat.completions.create(
            model="current",
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="none",
            response_format={"type": "json_object"},
        )
        return loads(response.choices[0].message.content)

    async def call_openai_llm(
        self, model: str, prompt: str, output_schema: type[BaseModel] | None = None
    ):
        if self.openai_client is None:
            self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await self.openai_client.chat.completions.parse(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="low",
            response_format=output_schema,
        )
        return response.choices[0].message.parsed

    async def inference(
        self, model: str, prompt: str, output_schema: type[BaseModel] | None = None
    ):
        if model in GOOGLE_LLM_OPTIONS:
            return await self.call_google_llm(model, prompt, output_schema)
        elif model in DEEPSEEK_LLM_OPTIONS:
            return await self.call_deepseek_llm(model, prompt, output_schema)
        elif model in LOCAL_LLM_OPTIONS:
            return await self.call_local_llm(model, prompt)
        elif model in OPENAI_LLM_OPTIONS:
            return await self.call_openai_llm(model, prompt, output_schema)
        else:
            raise ValueError(f"Unsupported model: {model}")

    def switch_model(self, current_model):
        models = GOOGLE_LLM_OPTIONS.union(DEEPSEEK_LLM_OPTIONS)
        model = random.choice(list(models - {current_model}))
        return model

    async def call_llm(
        self,
        model,
        prompt,
        retry=0,
        auto_switch_model=False,
        output_schema: type[BaseModel] | None = None,
    ):
        while retry >= 0:
            try:
                return await self.inference(model, prompt, output_schema)
            except Exception as e:
                print(f"LLM inference error for model {model}: {e}")
                retry -= 1
        if auto_switch_model:
            new_model = self.switch_model(model)
            print(f"Switching to alternative model: {new_model}")
            try:
                return await self.inference(new_model, prompt)
            except Exception as e:
                print(f"LLM inference error for model {model}: {e}")
                return None
        return None

    async def batch_translate(self, model: str, target_language: str, batch: list[str]):
        prompt = TRANSLATE_HTML_PROMPT.format(target_language, batch)
        response = await self.call_llm(model, prompt, retry=0, auto_switch_model=False)
        print(f"Translation response for model {model}: {response}")
        return response

    async def translate_single_chapter(
        self,
        chapter_text: str,
        model: str = "gpt-6-luna",
    ):
        print(f"Translating chapter with model {model}...")
        if model == "HachimiMT-60-QT":
            rows, _ = self.hachimi_translator.translate_text(chapter_text, chunk_mode="sentence", beam_size=2)
            if len(rows) < 2:
                return None
            title = rows[0][2]
            content = "\n".join(row[2] for row in rows[1:])
            return ChapterTranslationResult(title=title, content=content)
        else:
            prompt = TRANSLATE_BOOK_PROMPT.format(chapter_text=chapter_text)
            response = await self.call_llm(
                model, prompt, retry=1, auto_switch_model=False, output_schema=ChapterTranslationResult
            )
            return response

    def hachimi_translate(self, chapter_text: str):
        rows, _ = self.hachimi_translator.translate_text(chapter_text, chunk_mode="sentence", beam_size=2)
        return rows


def loads(s: str):
    """
    A drop-in replacement for `json.loads` that also tries to handle
    JSON responses wrapped in markdown code blocks or backticks.
    """
    # Attempt a direct parse first.
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        # We store the first exception to re-raise if all fallback attempts fail
        fallback_error = e

    # 1) Try triple backtick code blocks (with or without 'json' after the backticks).
    #    We use finditer to allow multiple code blocks in the string.
    triple_code_block_regex = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
    for match in triple_code_block_regex.finditer(s):
        snippet = match.group(1).strip()
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            # If the code block is invalid, keep trying subsequent blocks
            pass

    # 2) If that didn't work, look for inline backtick JSON (like `{"foo":"bar"}`).
    single_backtick_regex = re.compile(r"`([^`]*)`")
    match = single_backtick_regex.search(s)
    if match:
        snippet = match.group(1).strip()
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass

    # If none of the above parsing worked, re-raise the original JSONDecodeError.
    raise fallback_error


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


llm_client = LLMClient()
