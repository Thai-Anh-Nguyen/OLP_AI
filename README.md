# Môi trường luyện tập OLP AI - Vòng Sơ loại

Giả lập môi trường code của đề thi (Python 3.10 + đúng thư viện Bảng 1, không
pip/conda khi luyện) cho 3 máy khác kiến trúc (1 LOQ Windows/x86_64, 2 MacBook
Apple Silicon/arm64) dùng chung một image. Khác với đề thi thật: **Internet vẫn
mở** để gọi LLM online lúc luyện tập.

## Cài đặt 1 lần mỗi máy

- **LOQ (Windows):** cài Docker Desktop, bật WSL2 backend.
- **MacBook:** cài Docker Desktop for Mac (bản Apple Silicon).

## Lần build đầu tiên (chỉ 1 người trong team làm)

```bash
docker compose build
docker compose up -d
```

Mở `http://localhost:8888` trên trình duyệt là vào Jupyter Notebook, giống hệt
luồng "đăng nhập qua link web" của đề thi.

## Cấu hình LLM hỗ trợ code (khác đề thi thật - đề thi Vòng Sơ loại không có
mục này, đây là phần team tự thêm cho mục đích luyện tập)

Đề thi thật (Final) có cho dùng LLM offline nội bộ; Vòng Sơ loại thì không đề
cập gì tới LLM cả. Nhưng luyện tập mà không có ai hỗ trợ hỏi-đáp thì không sát
thực tế đội hình lúc thi, nên team tự thêm 1 lớp gọi LLM online, xem như "trợ
lý" tự chọn provider:

```bash
cp .env.example .env
# rồi sửa .env: điền LLM_BASE_URL / LLM_API_KEY / LLM_MODEL theo provider bạn
# có tài khoản (OpenRouter / Together AI / Fireworks / DeepInfra / ... - xem
# gợi ý ngay trong .env.example). .env đã bị .gitignore, mỗi người giữ key
# riêng, không commit lên git chung.
```

Trong notebook (`./workspace`), gọi qua helper có sẵn:

```python
from llm_helper import ask
print(ask("Giải thích ngắn gọn XGBoost hoạt động thế nào?"))
```

Có sẵn `workspace/00_llm_smoke_test.ipynb` để test nhanh key đã đúng chưa.
Đổi provider/model chỉ cần sửa `.env`, không đụng code.

## Chốt version chung cho cả 3 máy (làm 1 lần, quan trọng)

Lần build đầu, mỗi package sẽ tự lấy bản mới nhất tương thích (đúng tinh thần
"bản ổn định mới nhất tại thời điểm tổ chức" của đề thi). Để cả 3 máy có **y hệt
version**, người build đầu tiên chạy:

```bash
docker compose exec olpai-practice pip freeze > requirements.lock.txt
```

Commit `requirements.lock.txt` vào repo chung. Hai bạn còn lại chỉ cần
`git pull` rồi `docker compose build` — Dockerfile tự phát hiện file lock và
build từ đó thay vì resolve lại, nên 3 máy sẽ giống nhau tuyệt đối dù chip khác
nhau (miễn là có wheel cho từng kiến trúc, xem mục Lưu ý bên dưới).

Muốn cập nhật lại bộ thư viện (vd sau vài tháng): xoá `requirements.lock.txt`,
build lại từ `requirements.in`, rồi freeze lại.

## Dùng hằng ngày

```bash
docker compose up -d      # bật
docker compose down       # tắt (dữ liệu trong ./workspace vẫn còn)
```

Notebook lưu trong `./workspace` (bind-mount) nên có thể đồng bộ qua git giữa 3
máy như code bình thường.

## Lưu ý / các điểm dễ vỡ khi build

- **torch/torchvision**: cài bản CPU-only. Lưu ý: `--index-url` phải đặt thành
  dòng riêng ở đầu file `requirements.in` (global), viết chung 1 dòng với tên
  package (`torch --index-url ...`) sẽ KHÔNG có tác dụng — đã test thực tế bị
  tụt về PyPI mặc định và kéo theo ~2GB gói CUDA/NVIDIA không cần thiết, vì
  không máy nào trong team cần train nặng cục bộ (GPU thật sự chạy trên nền
  tảng của BTC lúc thi, máy team chỉ để luyện logic code).
- **fasttext**: dùng `fasttext-wheel` thay vì `fasttext` gốc (cùng
  `import fasttext`) vì bản gốc hay lỗi build C++ trên Python 3.10 + compiler
  mới, nhất là trên arm64 (MacBook).
- **autoviz**: kéo khá nhiều dependency phụ (hvplot, holoviews...), đôi khi
  đụng version với pandas/numpy mới. Nếu build lỗi ở bước này, có thể tạm bỏ
  dòng `autoviz` khỏi `requirements.in`, build phần còn lại trước, thêm lại
  sau khi kiểm tra riêng.
- **numpy 2.x**: nếu một thư viện nào báo lỗi không tương thích numpy 2, ghim
  `numpy<2` trong `requirements.in` rồi build lại.
- Toàn bộ image là **CPU-only, không có CUDA** — nếu sau này muốn LOQ (có GPU
  NVIDIA) chạy nặng hơn, làm riêng một Dockerfile biến thể cho máy đó, đừng
  trộn vào image dùng chung để tránh 2 MacBook build lỗi.

## Quy ước nhóm (không phải giới hạn kỹ thuật)

Image này vẫn có `pip`/`conda` bên trong (cần để build). Việc "không dùng
pip/conda khi luyện" là quy ước tự giác của team để tập phản xạ giống lúc thi
thật, không phải khoá cứng — giữ vậy sẽ linh hoạt hơn nếu cần cài thêm gì đó
để debug môi trường.
