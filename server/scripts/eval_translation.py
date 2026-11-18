import torch
from transformers import AutoTokenizer, MarianMTModel

tokenizer = AutoTokenizer.from_pretrained('../../models/hamichi-zh-vi-final/')
model = MarianMTModel.from_pretrained('../../models/hamichi-zh-vi-final/').eval()

src = """那又如何，那你有什么证据证明我们不是仅存的人类"""


with torch.inference_mode():
    sentences = src.splitlines()
    print(sentences)
    for sentence in sentences:
        if sentences:
            inp = tokenizer(sentence, return_tensors="pt", truncation=True, max_length=256)
            out = model.generate(**inp, max_new_tokens=300, num_beams=4, early_stopping=True)
            print(tokenizer.decode(out[0], skip_special_tokens=True))
