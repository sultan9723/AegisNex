"""Factory helpers for configured notification providers."""

from __future__ import annotations

from src.config import Config
from src.notifications.base import NotificationProvider
from src.notifications.discord import DiscordProvider
from src.notifications.email import EmailProvider
from src.notifications.slack import SlackProvider


def build_notification_providers(config: Config) -> list[NotificationProvider]:
    providers: list[NotificationProvider] = []
    email = config.notifications.email
    providers.append(
        EmailProvider(
            enabled=email.enabled,
            timeout_seconds=email.timeout_seconds,
            retry_attempts=email.retry_attempts,
            retry_delay_seconds=email.retry_delay_seconds,
            message_template=email.message_template,
            resolution_template=email.resolution_template,
            smtp_host=email.host,
            smtp_port=email.port,
            username=email.username,
            password=email.password,
            sender=email.sender or email.username,
            recipient=email.recipient,
            subject=email.subject,
            starttls=email.starttls,
        )
    )

    slack = config.notifications.slack
    providers.append(
        SlackProvider(
            enabled=slack.enabled,
            timeout_seconds=slack.timeout_seconds,
            retry_attempts=slack.retry_attempts,
            retry_delay_seconds=slack.retry_delay_seconds,
            message_template=slack.message_template,
            resolution_template=slack.resolution_template,
            webhook_url=slack.webhook_url,
        )
    )

    discord = config.notifications.discord
    providers.append(
        DiscordProvider(
            enabled=discord.enabled,
            timeout_seconds=discord.timeout_seconds,
            retry_attempts=discord.retry_attempts,
            retry_delay_seconds=discord.retry_delay_seconds,
            message_template=discord.message_template,
            resolution_template=discord.resolution_template,
            webhook_url=discord.webhook_url,
        )
    )
    return providers
