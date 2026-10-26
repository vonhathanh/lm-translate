import asyncio

from dotenv import load_dotenv

load_dotenv()

from database import *


async def main():
    for i in range(15):
        await add_book(Book(title=f"book_{i+1}"))
    book = await find_book("book_1")
    for i in range(20):
        await add_chapter(Chapter(index=i+1, title=f"Chapter_{i+1}", content="None", book_id=book.id))
    

if __name__ == "__main__":
    asyncio.run(main())