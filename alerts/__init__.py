"""Capa de notificaciones (WhatsApp via CallMeBot, Telegram, etc.)."""

from .notifier import enviar_alerta, get_notifier

__all__ = ["enviar_alerta", "get_notifier"]
