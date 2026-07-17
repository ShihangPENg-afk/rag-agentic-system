import time
from functools import lru_cache
from uuid import UUID

from redis import Redis

from app.core.config import REDIS_URL


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def increment_chat_rate_limit(
    user_id: UUID | str,
    limit: int = 20,
    window_seconds: int = 60,
) -> int:
    """
    Increment and return the current request count for a user in a fixed window.
    """
    window = int(time.time() // window_seconds)
    key = f"rate_limit:chat:{user_id}:{window}"
    client = get_redis_client()

    pipe = client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds + 5)
    count, _ = pipe.execute()
    return int(count)
