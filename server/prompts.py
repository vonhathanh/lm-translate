TRANSLATE_HTML_PROMPT = """Translate the following array of text to {}.
If the text already is in the target language, keep it as is. 
If the text is not translatable (e.g. a name, a brand, a product name, special characters), keep it as is.
Preserve the special characters order, for example, if the input text is: "#$% true", target language is Vietnamese, the output should be "#$% đúng", not "đúng".
Return an array of translated text preserving input order. 
EXAMPLE JSON OUTPUT:
{{
    "items": ["translated text 1", "translated text 2", "..."]
}}
Here is the input array: {}"""


TRANSLATE_BOOK_PROMPT = """
Dịch đoạn text tiếng Trung sau đây sang tiếng Việt. Tuân thủ nghiêm ngặt các quy tắc sau:

1. Từ vựng Hán Việt: Giữ tối đa các từ mang Hán Việt có thể, ví dụ: bổn tọa, tại hạ, lão phu, đạo hữu, tàn nhẫn, sát khí, hư không, thiên địa, bạch nguyệt quang...

2. Danh xưng và ngôi thứ: Giữ nguyên cách xưng hô đặc trưng (hắn, y, nàng, bọn cường giả, mỗ...). Không dịch thành anh/chị/ông/bà kiểu hiện đại.

3. Hệ thống tu luyện: Tuyệt đối giữ nguyên tên cảnh giới (Luyện Khí, Trúc Cơ, Nguyên Anh...), tên công pháp, pháp bảo, đan dược.

4. Thành ngữ: Dịch sang âm Hán Việt tương đương, hoặc dịch nghĩa sát nhất nhưng vẫn giữ vẻ cổ phong.

5. Cấu trúc câu: Dịch mượt mà, dễ đọc, tuyệt đối không thêm thắt ý kiến cá nhân hay bẻ cong ý nghĩa gốc của tác giả. 

[Nâng cao - tùy chọn]: Dịch mượt mà, giữ giọng văn sảng văn, thêm chút hài hước nếu nguyên tác có.

6. Dịch theo xu hướng convert một tý, không nên dịch sát quá.

7. Trả về kết quả theo dạng JSON với 2 phần: "title" (tên chương) và "content" (nội dung của chương)

EXAMPLE JSON OUTPUT:
{{
    "title": "string",
    "content": "string"
}}

Đây là đoạn text cần dịch:

{chapter_text}
"""