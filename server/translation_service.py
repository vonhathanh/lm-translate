import json
import os
import random
import re

from google import genai
from google.genai import Client, types
from openai import OpenAI
from prompts import TRANSLATE_BOOK_PROMPT, TRANSLATE_HTML_PROMPT
from pydantic import BaseModel

GOOGLE_LLM_OPTIONS = {
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-preview",
}

DEEPSEEK_LLM_OPTIONS = {
    "deepseek-v4-flash",
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


class ChapterTranslationResult(BaseModel):
    title: str
    content: str


class LLMClient:
    def __init__(self):
        self.gemini_client: Client = None
        self.deepseek_client: OpenAI = None
        self.local_llm_client: OpenAI = None
        self.openai_client: OpenAI = None

    def call_google_llm(self, model: str, prompt: str, output_schema: type[BaseModel] | None = None):
        if self.gemini_client is None:
            self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = self.gemini_client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=output_schema,
                        ),
                    )
        return response.parsed

    def call_deepseek_llm(self, model: str, prompt: str):
        if self.deepseek_client is None:
            self.deepseek_client = OpenAI(
                        api_key=os.environ.get("DEEP_SEEK_API_KEY"),
                        base_url="https://api.deepseek.com",
                    )
        response = self.deepseek_client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                    )
        return loads(response.choices[0].message.content)

    def call_local_llm(self, prompt: str):
        if self.local_llm_client is None:
            self.local_llm_client = OpenAI(
                        api_key=os.getenv("LOCAL_LLM_API_KEY"),
                        base_url=os.getenv("LOCAL_LLM_API_URL"),
                    )
        response = self.local_llm_client.chat.completions.create(
                        model="current",
                        messages=[{"role": "user", "content": prompt}],
                        reasoning_effort="none",
                        response_format={"type": "json_object"},
                    )
        return loads(response.choices[0].message.content)

    def call_openai_llm(self, model: str, prompt: str, output_schema: type[BaseModel] | None = None):
        if self.openai_client is None:
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = self.openai_client.chat.completions.parse(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        reasoning_effort="low",
                        response_format=output_schema,
                    )
        return response.choices[0].message.parsed


    def inference(self, model: str, prompt: str, output_schema: type[BaseModel] | None = None):
        if model in GOOGLE_LLM_OPTIONS:
            return self.call_google_llm(model, prompt, output_schema)
        elif model in DEEPSEEK_LLM_OPTIONS:
            return self.call_deepseek_llm(model, prompt)
        elif model == "localhost":
            return self.call_local_llm(prompt)
        elif model in OPENAI_LLM_OPTIONS:
            return self.call_openai_llm(model, prompt, output_schema)
        else:
            raise ValueError(f"Unsupported model: {model}")

    def switch_model(self, current_model):
        models = GOOGLE_LLM_OPTIONS.union(DEEPSEEK_LLM_OPTIONS)
        model = random.choice(list(models - {current_model}))
        return model

    async def call_llm(self, model, prompt, retry=0, auto_switch_model=False, output_schema: type[BaseModel] | None = None):
        while retry >= 0:
            try:
                return self.inference(model, prompt, output_schema)
            except Exception as e:
                print(f"LLM inference error for model {model}: {e}")
                retry -= 1
        if auto_switch_model:
            new_model = self.switch_model(model)
            print(f"Switching to alternative model: {new_model}")
            try:
                return self.inference(new_model, prompt)
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
        prompt = TRANSLATE_BOOK_PROMPT.format(chapter_text=chapter_text)
        response = await self.call_llm(model, prompt, retry=1, auto_switch_model=False, output_schema=ChapterTranslationResult)
        return response


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
    triple_code_block_regex = re.compile(
        r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE
    )
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
