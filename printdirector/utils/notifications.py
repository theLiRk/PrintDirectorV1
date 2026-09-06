import logging

import aiohttp

log = logging.getLogger(__name__)


class WebhookNotifier:
    def __init__(self, config):
        self.config = config

    def should_send(self, event):
        return (
            self.config.enabled
            and bool(self.config.webhook_url)
            and event.get("type") in set(self.config.events)
        )

    async def send(self, event, force=False):
        if force:
            if not self.config.webhook_url:
                return False
        elif not self.should_send(event):
            return False
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        payload = {"source": "PrintDirector", **event}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.config.webhook_url, json=payload) as response:
                    if response.status >= 400:
                        log.warning("Notification webhook returned HTTP %s", response.status)
                        return False
        except (aiohttp.ClientError, TimeoutError) as exc:
            log.warning("Notification webhook failed: %s", exc)
            return False
        return True
