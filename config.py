"""
配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API配置
API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
MODEL_NAME = "qwen-plus"
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
).strip()
if not API_KEY:
    raise RuntimeError("缺少环境变量 DASHSCOPE_API_KEY")
    
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