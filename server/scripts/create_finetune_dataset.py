import json

DATASET_LENGTH = 2

new_dataset = []
with open("/Users/hanhvn/.cache/huggingface/hub/datasets--kaihe--chinese_vietnamese_bilingual_wangwen/snapshots/521f34d794a5d3208a0d9fae1d4732e38c851564/parallel_sentences.jsonl", "r", encoding="utf-8") as f:
    i = 0
    for i, line in enumerate(f):  # Read the first 100 lines
        if not line.strip():  # Skip empty lines
            continue

        sentences = json.loads(line)["sentences"]
        print(f'got {len(sentences)} sentences')
        print(f'processing {i}th record')
        for pair in sentences:
            if len(pair) != 2:
                continue;
            source, target = pair[1], pair[0]
            new_dataset.append({'source': source, 'target': target})

        if i >= DATASET_LENGTH:
            break

with open("./kamichi_finetune.jsonl", "a", encoding='utf-8') as f:
    for pair in new_dataset:
        f.write(json.dumps(pair, ensure_ascii=False))
        f.write('\n')
    print('finished')