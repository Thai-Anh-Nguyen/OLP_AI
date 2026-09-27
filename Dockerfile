FROM python:3.10-slim-bookworm

# Thư viện hệ thống cần cho: opencv-python (libgl/libglib...), build native
# extension (catboost/xgboost/fasttext-wheel đa phần có sẵn wheel, nhưng vẫn
# giữ toolchain phòng khi pip phải build từ source trên kiến trúc lạ, vd arm64 Mac).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN pip install --no-cache-dir --upgrade pip

# Ưu tiên dùng requirements.lock.txt nếu đã có (sau khi cả team đã freeze),
# nếu chưa có thì build từ requirements.in (bản build đầu tiên, tự resolve
# "bản ổn định mới nhất" giống tinh thần đề thi).
COPY requirements.in ./
COPY requirements.lock.tx[t] ./
RUN if [ -f requirements.lock.txt ]; then \
        pip install --no-cache-dir -r requirements.lock.txt; \
    else \
        pip install --no-cache-dir -r requirements.in; \
    fi

# Bake sẵn dữ liệu phụ trợ của spacy/nltk ở bước build (dùng Internet lúc build
# image - hợp lệ vì đây là môi trường TRAINING, không phải giờ thi thật) để lúc
# luyện tập không phải phụ thuộc mạng, giống cảm giác "đã cài sẵn" như đề thi.
RUN python -m spacy download en_core_web_sm \
    && python -c "import nltk; [nltk.download(p) for p in ['punkt','punkt_tab','stopwords','wordnet','averaged_perceptron_tagger']]"

EXPOSE 8888

# Không đặt token: dùng nội bộ trong mạng máy mỗi thành viên, không expose ra internet.
CMD ["jupyter", "notebook", \
     "--ip=0.0.0.0", "--port=8888", "--no-browser", \
     "--allow-root", "--NotebookApp.token=", "--NotebookApp.password="]
