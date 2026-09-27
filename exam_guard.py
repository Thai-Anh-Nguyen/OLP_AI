# ==== OLP AI exam guard ====
# Dán toàn bộ file này vào CELL ĐẦU TIÊN của phần làm bài (Colab / Kaggle / Jupyter).
# Trước cell này chỉ nên có cell "setup": mount Drive, copy dữ liệu, cài các thư viện
# Bảng 1 mà Colab/Kaggle còn thiếu (guard sẽ in lệnh cài cần thiết).
# Sau cell này, notebook bị giới hạn giống đề thi:
#   1. Chỉ import được thư viện trong Bảng 1 + thư viện chuẩn của Python.
#   2. Chặn !pip / %pip / conda / apt.
#   3. Chặn tải model/dữ liệu từ Internet (HuggingFace offline + chặn kết nối ra ngoài).
# Chạy lại cell này nhiều lần không sao. Muốn tắt hẳn: Restart kernel.

import builtins
import ipaddress
import os
import re
import socket
import sys
from importlib import metadata

# Tên dùng khi import (khác tên package pip: sklearn, cv2, PIL, skimage...).
ALLOWED = {
    "torch", "tensorflow", "sklearn", "xgboost", "catboost", "transformers", "spacy", "nltk", "gensim", "fasttext",
    "pandas", "numpy", "scipy",
    "cv2", "PIL", "torchvision", "skimage",
    "matplotlib", "seaborn", "plotly", "autoviz",
    "joblib", "datasets", "evaluate", "pytorch_lightning", "tensorboard", "tqdm",
    "keras",    # cài kèm tensorflow, trong môi trường thi cũng import được
    "IPython",  # hạ tầng notebook (display, ...)
}
ALLOWED_PREFIXES = ("google.colab",)  # vd: from google.colab import drive
EXTRA_ALLOWED: set[str] = set()      # tự thêm nếu team thống nhất cho phép thêm thư viện nào đó
BLOCK_INTERNET = True

# Tên package pip để kiểm tra version; tuple = các tên thay thế tương đương.
BANG_1 = [
    "torch", "tensorflow", "scikit-learn", "xgboost", "catboost", "transformers", "spacy", "nltk", "gensim",
    ("fasttext", "fasttext-wheel"), "pandas", "numpy", "scipy",
    ("opencv-python", "opencv-python-headless", "opencv-contrib-python"), "Pillow", "torchvision", "scikit-image",
    "matplotlib", "seaborn", "plotly", "autoviz",
    "joblib", "datasets", "evaluate", "pytorch-lightning", "tensorboard", "tqdm",
]


def _report_versions():
    print(f"Python {sys.version.split()[0]}" + ("" if sys.version_info[:2] == (3, 10) else "  (đề thi dùng 3.10 - khác biệt nhỏ, bỏ qua được)"))
    missing = []
    for entry in BANG_1:
        names = entry if isinstance(entry, tuple) else (entry,)
        for name in names:
            try:
                print(f"  {name:<22} {metadata.version(name)}")
                break
            except metadata.PackageNotFoundError:
                continue
        else:
            missing.append(names[-1] if names[0] == "fasttext" else names[0])
    if missing:
        print(f"\nTHIẾU {len(missing)} thư viện Bảng 1. Cài ở cell setup TRƯỚC guard (rồi chạy lại guard):")
        print(f"  !pip install -q {' '.join(missing)}")


# --- 1. Chặn import ngoài Bảng 1 (chỉ với code trong notebook; thư viện tự import gì bên trong thì kệ) ---
_orig_import = getattr(builtins, "_exam_guard_orig_import", builtins.__import__)
builtins._exam_guard_orig_import = _orig_import


def _import_allowed(name):
    top = name.split(".")[0]
    return (
        top in sys.stdlib_module_names
        or top in ALLOWED
        or top in EXTRA_ALLOWED
        or any(name == p or name.startswith(p + ".") for p in ALLOWED_PREFIXES)
    )


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and globals is not None and globals.get("__name__") == "__main__" and not _import_allowed(name):
        raise ImportError(f"[exam guard] '{name}' không có trong Bảng 1 - lúc thi sẽ không import được.")
    return _orig_import(name, globals, locals, fromlist, level)


builtins.__import__ = _guarded_import

# --- 2. Chặn cài thư viện / tải file bằng lệnh shell trong notebook ---
_INSTALL = re.compile(r"^\s*[!%]{1,2}\s*(sudo\s+)?(pip3?|conda|mamba|micromamba|uv|apt(-get)?)\b")
_DOWNLOAD = re.compile(r"^\s*!\s*(sudo\s+)?(wget|curl|gdown|git\s+clone|huggingface-cli|hf\s+download|kaggle)\b")
_SHELL_CELL = re.compile(r"^\s*%%(bash|sh|script)\b")


def _block_commands(lines):
    is_shell = bool(lines) and _SHELL_CELL.match(lines[0])
    for line in lines:
        probe = "!" + line if is_shell else line
        if _INSTALL.match(probe):
            reason = "không được cài thêm thư viện (pip/conda)"
        elif BLOCK_INTERNET and _DOWNLOAD.match(probe):
            reason = "không được tải dữ liệu/model từ Internet"
        else:
            continue
        return [f"raise RuntimeError({f'[exam guard] Cell bị chặn: {reason} -> {line.strip()}'!r})\n"]
    return lines


_block_commands._exam_guard = True
try:
    _ip = get_ipython()  # noqa: F821 - chỉ có khi chạy trong Jupyter/Colab/Kaggle
    _ip.input_transformers_cleanup[:] = [t for t in _ip.input_transformers_cleanup if not getattr(t, "_exam_guard", False)]
    _ip.input_transformers_cleanup.append(_block_commands)
except NameError:
    pass

# --- 3. Chặn Internet: HF chạy offline + chặn mọi kết nối ra địa chỉ public ---
# Mạng nội bộ/loopback vẫn cho phép để không làm hỏng kernel, Drive, ... của Colab.
if BLOCK_INTERNET:
    if {"transformers", "huggingface_hub", "datasets"} & sys.modules.keys():
        print("CẢNH BÁO: transformers/datasets đã được import trước guard -> Restart kernel, chạy guard trước.")
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[var] = "1"

    _orig_connect = getattr(socket.socket, "_exam_guard_orig_connect", socket.socket.connect)
    _orig_connect_ex = getattr(socket.socket, "_exam_guard_orig_connect_ex", socket.socket.connect_ex)
    socket.socket._exam_guard_orig_connect = _orig_connect
    socket.socket._exam_guard_orig_connect_ex = _orig_connect_ex

    def _is_local(address):
        if not isinstance(address, tuple):
            return True  # Unix socket
        host = str(address[0]).split("%")[0]
        if host == "localhost":
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return ip.is_loopback or ip.is_private or ip.is_link_local

    def _connect(self, address):
        if not _is_local(address):
            raise ConnectionRefusedError(f"[exam guard] Chặn kết nối Internet tới {address[0]} (lúc thi bị chặn tải từ Internet)")
        return _orig_connect(self, address)

    def _connect_ex(self, address):
        if not _is_local(address):
            return 111  # ECONNREFUSED
        return _orig_connect_ex(self, address)

    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex

print("=== EXAM GUARD ĐANG BẬT ===")
print(f"Import: chỉ Bảng 1 + stdlib{' + ' + ', '.join(sorted(EXTRA_ALLOWED)) if EXTRA_ALLOWED else ''} | pip/conda: chặn | Internet: {'chặn' if BLOCK_INTERNET else 'MỞ'}")
_report_versions()
