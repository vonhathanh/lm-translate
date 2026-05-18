from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dto import Item


app = FastAPI()

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

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/api/v1/translate")
def translate_page(item: Item):
    # Placeholder implementation - replace with actual translation logic
    return {"translatedText": item.text}