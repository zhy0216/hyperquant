import logging
from collections import deque

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool = True, max_queue: int = 100) -> None:
        self._chat_id = chat_id
        self._enabled = enabled
        self._max_queue = max_queue
        self._failed_queue: deque[str] = deque(maxlen=max_queue)
        self._bot = None
        if enabled and token:
            try:
                from telegram import Bot
                self._bot = Bot(token=token)
            except ImportError:
                logger.warning("python-telegram-bot not installed, notifications will be disabled unless bot is set manually")

    async def send(self, message: str) -> None:
        if not self._enabled or not self._bot:
            return
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=message)
        except Exception:
            logger.warning("Telegram send failed, queued message")
            self._failed_queue.append(message)

    async def retry_failed(self) -> None:
        if not self._enabled or not self._bot:
            return
        retries = list(self._failed_queue)
        self._failed_queue.clear()
        for msg in retries:
            await self.send(msg)
