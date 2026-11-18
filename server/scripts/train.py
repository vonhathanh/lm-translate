import numpy as np
import sacrebleu
from datasets import load_dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)

MODEL = "ngocdang83/HachimiMT-60-QT"
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL)

# --- data ---
raw = load_dataset("json", data_files="kamichi_finetune.jsonl")

# Split 90% train, 10% test (use seed for reproducibility)
split_dataset = raw["train"].train_test_split(test_size=0.1, seed=1993)

def preprocess(batch):
    return tok(batch["source"], text_target=batch["target"],
               max_length=512, truncation=True)

# raw_small = DatasetDict({
#     split: dataset.select(range(min(1000, len(dataset))))
#     for split, dataset in split_dataset.items()
# })

data = split_dataset.map(preprocess, batched=True,
               remove_columns=raw["train"].column_names)

print("train size:", len(data["train"]))

dev_small = data["test"].select(range(1000))   # keep in-training eval fast

# --- metrics ---
def compute_metrics(eval_pred):
    preds, labels = eval_pred
    preds = np.where(preds != -100, preds, tok.pad_token_id)
    labels = np.where(labels != -100, labels, tok.pad_token_id)
    hyp = tok.batch_decode(preds, skip_special_tokens=True)
    ref = tok.batch_decode(labels, skip_special_tokens=True)
    return {
        "bleu": sacrebleu.corpus_bleu(hyp, [ref]).score,
        "chrf": sacrebleu.corpus_chrf(hyp, [ref]).score,
    }

# --- training config ---
args = Seq2SeqTrainingArguments(
    output_dir="hamichi-zh-vi-ft",
    per_device_train_batch_size=32,
    per_device_eval_batch_size=64,
    gradient_accumulation_steps=2,      # effective batch 64
    learning_rate=3e-5,
    num_train_epochs=1.5,
    weight_decay=0.01,
    label_smoothing_factor=0.1,
    eval_strategy="steps",              # "evaluation_strategy" in older versions
    eval_steps=2000,
    save_steps=2000,
    save_total_limit=3,
    logging_steps=100,
    predict_with_generate=True,
    generation_max_length=128,
    generation_num_beams=1,             # greedy during training-time eval, for speed
    load_best_model_at_end=True,
    metric_for_best_model="chrf",
    fp16=False,                         # keep fp32 on MPS
    report_to="none",
)

trainer = Seq2SeqTrainer(
    model=model, args=args,
    train_dataset=data["train"], eval_dataset=dev_small,
    data_collator=DataCollatorForSeq2Seq(tok, model=model),
    compute_metrics=compute_metrics,
)

trainer.train()
trainer.save_model("hamichi-zh-vi-final")
tok.save_pretrained("hamichi-zh-vi-final")