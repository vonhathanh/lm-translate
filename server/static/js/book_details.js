import { load } from "./common.js";

(function () {
  const startReadingBtn = document.getElementById("start_reading_btn");
  if (startReadingBtn) {
    const bookId = startReadingBtn.dataset.bookId;
    const state = load(`book_${bookId}`);
    if (state.lastChapterIndex) {
      startReadingBtn.href = `/api/v1/chapter/${bookId}/${state.lastChapterIndex}`;
      startReadingBtn.textContent = `Đọc tiếp Chương ${state.lastChapterIndex}`;
    } else {
        startReadingBtn.href = `/api/v1/chapter/${bookId}/1`;
        startReadingBtn.textContent = "Đọc từ đầu";
    }
  }
})()