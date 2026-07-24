"""
应用配置。
"""
import os

from dotenv import load_dotenv

load_dotenv()

# API 配置
API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
MODEL_NAME = "qwen-plus"
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).strip()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "dashscope").strip().lower()
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v1").strip()
if not API_KEY and EMBEDDING_PROVIDER != "fake":
    raise RuntimeError("缺少环境变量 DASHSCOPE_API_KEY")

# rerank provider: mock(默认，便于离线/测试) 或 none(不调整顺序，仅补齐 rerank_score)
RERANK_PROVIDER = os.getenv("RERANK_PROVIDER", "mock").strip().lower()
RAG_MIN_CONFIDENCE = float(os.getenv("RAG_MIN_CONFIDENCE", "0.0") or "0.0")

# 文本处理配置
CHUNK_SIZE = 300
CHUNK_OVERLAP = 50
MIN_CHUNK_LENGTH = 20

# 向量配置
FIXED_DIMENSION = 1536
TOP_K = 5
FINAL_TOP_K = 3
DISTANCE_THRESHOLD = 1.2
SCORE_THRESHOLD_PERCENT = 0.6
SIMILARITY_THRESHOLD = 0.85

# 上下文配置
MAX_PROMPT_LENGTH = 5500
SAFE_RESERVE_LENGTH = 800
CONTEXT_TRUNCATE_STEP = 200

# 网络配置
NETWORK_TIMEOUT = 5
NETWORK_CHECK_URL = "https://dashscope.aliyun.com"

# 工业设备健康预测 API
HEALTH_API_URL = os.getenv("HEALTH_API_URL", "http://127.0.0.1:8010").strip()
HEALTH_API_TIMEOUT = int(os.getenv("HEALTH_API_TIMEOUT", "30"))

# JWT 认证配置
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-change-me").strip()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip()
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Redis 配置：用于轻量接口限流
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
