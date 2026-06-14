"""
Envío de alertas.

`enviar_alerta(texto)` es la función aislada que usa el resto del sistema. Por
detrás hay una interfaz genérica `Notifier` con dos implementaciones:
CallMeBot (WhatsApp, por defecto) y Telegram. Cambiar de canal es solo setear
ALERT_BACKEND=telegram y las env vars correspondientes.
"""

from __future__ import annotations

import logging
import os
import urllib.parse

import requests

import config

log = logging.getLogger(__name__)


class Notifier:
    """Contrato genérico de canal de notificación."""

    nombre = "base"

    def disponible(self) -> bool:
        return True

    def enviar(self, texto: str) -> bool:
        raise NotImplementedError


class CallMeBotWhatsApp(Notifier):
    """WhatsApp gratis via CallMeBot (https://www.callmebot.com/blog/free-api-whatsapp-messages/)."""

    nombre = "callmebot-whatsapp"
    ENDPOINT = "https://api.callmebot.com/whatsapp.php"

    def __init__(self) -> None:
        self.phone = os.getenv("CALLMEBOT_PHONE")
        self.apikey = os.getenv("CALLMEBOT_APIKEY")

    def disponible(self) -> bool:
        return bool(self.phone and self.apikey)

    def enviar(self, texto: str) -> bool:
        params = {
            "phone": self.phone,
            "text": texto,          # urlencode se encarga del escaping
            "apikey": self.apikey,
        }
        url = f"{self.ENDPOINT}?{urllib.parse.urlencode(params)}"
        resp = requests.get(url, timeout=config.HTTP_TIMEOUT)
        ok = resp.ok
        if not ok:
            log.error("CallMeBot respondió %s: %s", resp.status_code, resp.text[:200])
        return ok


class TelegramNotifier(Notifier):
    """Canal alternativo: Telegram Bot API. Listo para cambiar fácil después."""

    nombre = "telegram"

    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def disponible(self) -> bool:
        return bool(self.token and self.chat_id)

    def enviar(self, texto: str) -> bool:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        resp = requests.post(
            url,
            data={"chat_id": self.chat_id, "text": texto, "disable_web_page_preview": False},
            timeout=config.HTTP_TIMEOUT,
        )
        ok = resp.ok
        if not ok:
            log.error("Telegram respondió %s: %s", resp.status_code, resp.text[:200])
        return ok


_BACKENDS = {
    "callmebot": CallMeBotWhatsApp,
    "whatsapp": CallMeBotWhatsApp,
    "telegram": TelegramNotifier,
}


def get_notifier() -> Notifier:
    cls = _BACKENDS.get(config.ALERT_BACKEND, CallMeBotWhatsApp)
    return cls()


def enviar_alerta(texto: str) -> bool:
    """
    Envía una alerta por el canal configurado. Nunca lanza excepción: loguea y
    devuelve False si falla, para no tumbar la barrida por un error de red.
    """
    notifier = get_notifier()
    if not notifier.disponible():
        log.warning(
            "Canal '%s' no configurado (faltan env vars); alerta NO enviada:\n%s",
            notifier.nombre, texto,
        )
        return False
    try:
        ok = notifier.enviar(texto)
        if ok:
            log.info("Alerta enviada por %s", notifier.nombre)
        return ok
    except Exception as exc:  # noqa: BLE001 - aislamos cualquier error de red
        log.error("Error enviando alerta por %s: %s", notifier.nombre, exc)
        return False
