from typing import List, Optional

from loguru import logger
from redis.asyncio import Redis

from src.application.protocols import WebhookDAO
from src.core.storage.keys import WebhookLockKey
from src.core.utils import json_utils


class WebhookDAOImpl(WebhookDAO):
    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_hash_exists(self, bot_id: int, webhook_hash: str) -> bool:
        key = WebhookLockKey(bot_id=bot_id, webhook_hash=webhook_hash)
        exists = await self.redis.exists(key.pack())

        if exists:
            logger.debug(f"Webhook hash '{webhook_hash}' found for bot '{bot_id}'")

        return bool(exists)

    async def save_hash(self, bot_id: int, webhook_hash: str) -> None:
        key = WebhookLockKey(bot_id=bot_id, webhook_hash=webhook_hash)
        await self.redis.set(name=key.pack(), value=json_utils.encode(None))
        logger.debug(f"Webhook lock key '{key.pack()}' saved to storage")

    async def clear_all_hashes(self, bot_id: int) -> None:
        pattern_key = WebhookLockKey(bot_id=bot_id, webhook_hash="*")
        keys: List[bytes] = await self.redis.keys(pattern_key.pack())

        if not keys:
            logger.debug(f"No webhook lock keys found to clear for bot '{bot_id}'")
            return

        await self.redis.delete(*keys)
        logger.info(f"Cleared '{len(keys)}' old webhook lock keys for bot '{bot_id}'")

    async def get_current_hash(self, bot_id: int) -> Optional[str]:
        pattern_key = WebhookLockKey(bot_id=bot_id, webhook_hash="*")
        keys: list[bytes] = await self.redis.keys(pattern_key.pack())

        if not keys:
            logger.debug(f"No webhook hash found in storage for bot '{bot_id}'")
            return None

        raw_key: str = keys[0].decode()
        current_hash: str = raw_key.split(":")[-1]

        logger.debug(f"Retrieved current hash '{current_hash}' for bot '{bot_id}'")
        return current_hash
