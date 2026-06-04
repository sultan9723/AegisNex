"""Notification providers for AegisNex incidents."""

from src.notifications.base import NotificationProvider, NotificationResult
from src.notifications.discord import DiscordProvider
from src.notifications.email import EmailProvider
from src.notifications.slack import SlackProvider

__all__ = [
    "DiscordProvider",
    "EmailProvider",
    "NotificationProvider",
    "NotificationResult",
    "SlackProvider",
]
