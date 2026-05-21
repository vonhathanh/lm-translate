import json
import os
import random

from google import genai
from google.genai import types
from openai import OpenAI

from dto import TranslationOutput


TRANSLATION_PROMPT = """Translate the following array of text to {}.
If the text already is in the target language, keep it as is. 
If the text is not translatable (e.g. a name, a brand, a product name, special characters), keep it as is.
Preserve the special characters order, for example, if the input text is: "#$% true", target language is Vietnamese, the output should be "#$% đúng", not "đúng".
Return an array of translated text preserving input order. 
EXAMPLE JSON OUTPUT:
{{
    "items": ["translated text 1", "translated text 2", "..."]
}}
Here is the input array: {}"""

GOOGLE_LLM_OPTIONS = {
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-preview",
}

DEEPSEEK_LLM_OPTIONS = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
}

class LLMClient:

    def __init__(self):
        self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.deepseek_client = OpenAI(
            api_key=os.environ.get('DEEP_SEEK_API_KEY'),
            base_url="https://api.deepseek.com"
        )

    def inference(self, model, prompt):
        if model in GOOGLE_LLM_OPTIONS:
            response = self.gemini_client.models.generate_content(
                model=model, 
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TranslationOutput,
                ),
            )
            parsed: TranslationOutput = response.parsed
            return parsed.items
        elif model in DEEPSEEK_LLM_OPTIONS:
            response = self.deepseek_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)["items"]
        else:
            raise ValueError(f"Unsupported model: {model}")
        
    def switch_model(self, current_model):
        models = GOOGLE_LLM_OPTIONS.union(DEEPSEEK_LLM_OPTIONS)
        model =  random.choice(list(models - {current_model}))
        return model

    async def call_llm(self, model, prompt, retry=0, auto_switch_model=False):
        while retry >= 0:
            try:
                return self.inference(model, prompt)
            except Exception as e:
                print(f"LLM inference error for model {model}: {e}")
                retry -= 1
        if auto_switch_model:
            new_model = self.switch_model(model)
            print(f"Switching to alternative model: {new_model}")
            try:
                return self.inference(new_model, prompt)
            except Exception as e:
                return None
        return None

    async def translate(self, model: str, target_language: str, batch: list[str]):
        prompt = TRANSLATION_PROMPT.format(target_language, batch)
        return await self.call_llm(model, prompt, retry=1, auto_switch_model=True)
