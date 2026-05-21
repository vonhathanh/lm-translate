TRANSLATION_PROMPT = """Translate the following array of text to {}.
If the text already is in the target language, keep it as is. 
If the text is not translatable (e.g. a name, a brand, a product name, special characters), keep it as is.
Preserve the special characters order, for example, if the input text is: "#$% true", target language is Vietnamese, the output should be "#$% đúng", not "đúng".
Return an array of translated text preserving input order. 
Here is the input array: {}"""
