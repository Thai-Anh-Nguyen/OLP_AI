# Bộ công cụ luyện thi OLP AI - Vòng Sơ loại

Team train trên Colab/Kaggle (có GPU, giống nền tảng notebook web của BTC). Repo
này chỉ thêm 2 thứ để luyện sát luật thi:

| | Là gì | Chạy ở đâu |
|---|---|---|
| `chat/` | Trang chat LLM tối giản: chỉ text, không upload, không tool | Laptop của mỗi người |
| `exam_guard.py` | Cell khoá notebook theo luật thi | Cell đầu của notebook Colab/Kaggle |

## 1. Chat LLM (`chat/`)

Mô phỏng chatbot của kỳ thi: một tab trình duyệt riêng, tách khỏi notebook, code
phải copy-paste tay qua lại. Chỉ cần Python 3 có sẵn trên máy, không cài gì thêm.

```bash
cd chat
cp .env.example .env      # rồi điền key riêng của bạn - xem hướng dẫn trong file
python3 server.py
```

Mở `http://localhost:8000`.

- **Key + fallback**: mỗi người một bộ key riêng trong `chat/.env` (đã bị
  `.gitignore`). Server thử lần lượt 4 provider free, cái nào hết quota / lỗi thì
  tự chuyển sang cái kế tiếp. Dưới mỗi câu trả lời có ghi model nào đã trả lời.

  | # | Provider | Model | Quota free |
  |---|---|---|---|
  | 1 | Cloudflare | `deepseek-r1-distill-qwen-32b` (đúng model thi) | ~10-20 câu/ngày |
  | 2 | Groq | `qwen3.8-27b` | 1.000 req/ngày, 8K token/phút |
  | 3 | OpenRouter | `qwen3.8-27b:free` | 50 req/ngày |
  | 4 | NVIDIA | `nemotron-3-nano-omni-30b-a3b-reasoning` | ~40 req/phút |

  Cách lấy từng key có ghi ngay trong `.env.example`. Không cần điền đủ cả 4.
  Groq giới hạn 8K token/phút, nên hội thoại dài hay bị chuyển sang provider
  sau - bấm "Chat mới" khi đổi chủ đề để đỡ tốn quota.
- **Khoá LLM theo giờ** (luật Final: chỉ dùng 5 tiếng đầu):
  `CHAT_LOCK_AFTER_HOURS=5 python3 server.py` - bắt đầu đếm từ lúc bật server.
  Không đặt thì không khoá.
- **Đổi port**: `CHAT_PORT=8080 python3 server.py`.
- Phần suy nghĩ `<think>` của R1 được thu gọn, bấm để xem. Phần này không gửi
  lại vào lịch sử hội thoại.

PDF Vòng Sơ loại không nhắc gì tới LLM, nên có thể vòng này không có chatbot.
Nên luyện cả vài buổi không dùng chat.

## 2. Exam guard (`exam_guard.py`)

Colab/Kaggle cài sẵn rất nhiều thứ ngoài Bảng 1 (lightgbm, requests...) và cho
tải model thoải mái - lúc thi thì không. Guard chặn các thứ đó.

Cấu trúc notebook luyện tập:

1. **Cell setup** (không tính là bài thi): mount Drive / copy dữ liệu, cài các
   thư viện Bảng 1 mà Colab/Kaggle còn thiếu.
2. **Cell guard**: dán toàn bộ nội dung `exam_guard.py`. Guard in version các
   thư viện và in sẵn lệnh `!pip install ...` cho thư viện nào còn thiếu
   (chép lệnh đó lên cell setup, chạy lại).
3. **Từ đây là bài làm**, bị giới hạn giống đề thi:
   - chỉ import được Bảng 1 + thư viện chuẩn của Python;
   - `!pip`, `%pip`, `conda`, `apt` bị chặn;
   - không tải được gì từ Internet (`from_pretrained`, `!wget`, `requests`...).
     Mạng nội bộ vẫn chạy để không làm hỏng Colab.

Mẹo:
- **Kaggle**: tắt luôn Internet trong Settings của notebook - giống đề thi
  nhất. Nhưng khi Internet tắt thì không `pip install` được, nên thư viện Bảng 1
  nào Kaggle không có sẵn sẽ không dùng được.
- **Colab**: không tắt được Internet, nên guard là thứ duy nhất chặn tải model.
- Guard không chặn được mọi cách lách (vd `importlib.import_module`,
  `subprocess`). Nó để tránh *vô tình* dùng thứ không được phép, không phải để
  chống gian lận.
- Cần mở thêm thư viện nào đó thì sửa `EXTRA_ALLOWED`, cần Internet thì đặt
  `BLOCK_INTERNET = False` ở đầu file.

## Luật thi cần nhớ khi luyện (Vòng Sơ loại)

- Giờ 0-5: làm bài trên train + public test. Giờ 6: BTC mới đưa mật khẩu private
  test để chạy ra file kết quả.
- Nộp 1 file `.zip` gồm file kết quả (`.csv` / `.pkl`) và file `.ipynb`.
  Notebook chạy tuần tự từ trên xuống phải ra đúng file kết quả đó -> trước khi
  nộp luôn "Restart & Run all" để kiểm tra.
- Có giới hạn số lần nộp, nộp trễ không được chấp nhận.
