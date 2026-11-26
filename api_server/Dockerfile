FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Keep Python dependencies explicit so PPT/DOCX generation does not fail at runtime.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "crewai[tools]>=1.15.2,<2.0.0" \
        "fastapi>=0.139.0" \
        "uvicorn>=0.51.0" \
        "python-dotenv>=1.0.0,<2.0.0" \
        "chromadb>=1.1.1,<2.0.0" \
        "python-docx>=1.2.0,<2.0.0" \
        "json-repair>=0.30.0" \
        "python-pptx>=1.0.0,<2.0.0"

COPY api_server/ ./api_server/
COPY agents/ ./agents/
COPY core/ ./core/
COPY crews/ ./crews/
COPY db/ ./db/
COPY schemas/ ./schemas/
COPY tools/ ./tools/
COPY utils/ ./utils/
COPY knowledge/ ./knowledge/
COPY config.py main.py ./

RUN mkdir -p /app/runtime/output /app/runtime/chroma_data /app/runtime/logs /app/runtime/data/materials

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# ⚠️ 不要加 --workers，也不要水平扩容多个 backend 副本。
#
# 本应用把运行状态保存在模块级变量里（见 api_server/deps.py），
# 每个进程各持一份、彼此不共享。一旦跑多进程会出现：
#   · 登录限流（10 次/分）实际变成 10×N 次，限流形同虚设
#   · 下载票据在 A 进程签发、请求落到 B 进程 → 404（时好时坏，最难排查）
#   · 自适应掌握度随机回退（取决于请求命中哪个进程）
#   · 消融实验并发上限 2 变成 2×N，可能同时打出多个大模型调用
#
# 要支持多进程，必须先把限流器 / 文件票据 / 自适应状态外部化到
# Redis 或共享存储，再回来加 --workers。
CMD ["uvicorn", "api_server.main:app", "--host", "0.0.0.0", "--port", "8000"]