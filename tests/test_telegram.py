from unittest.mock import AsyncMock

from notify.telegram import TelegramNotifier


async def test_send_message_calls_bot():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=True)
    notifier._bot = AsyncMock()
    await notifier.send("Test message")
    notifier._bot.send_message.assert_called_once_with(chat_id="12345", text="Test message")

async def test_send_failure_does_not_raise():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=True)
    notifier._bot = AsyncMock()
    notifier._bot.send_message.side_effect = Exception("Network error")
    await notifier.send("Test message")

async def test_disabled_notifier_is_noop():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=False)
    notifier._bot = AsyncMock()
    await notifier.send("Test message")
    notifier._bot.send_message.assert_not_called()

async def test_queue_cap_drops_oldest():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=True, max_queue=3)
    notifier._bot = AsyncMock()
    notifier._bot.send_message.side_effect = Exception("fail")
    for i in range(5):
        await notifier.send(f"msg {i}")
    assert len(notifier._failed_queue) <= 3
