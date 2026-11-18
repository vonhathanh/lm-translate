from datasets import load_dataset

ds = load_dataset("ngocdang83/tran-vi-teacher", "default")
train_ds = ds["train"]
print(train_ds[0])
