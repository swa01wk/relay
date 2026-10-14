"""Sending email: SMTP in production, the gateway log in development.

Configure SMTP with ``RELAY_SMTP_HOST`` (+ ``RELAY_SMTP_PORT``, ``RELAY_SMTP_USERNAME``,
``RELAY_SMTP_PASSWORD``, ``RELAY_SMTP_STARTTLS``) and ``RELAY_EMAIL_FROM``. Without a host,
messages are written to the log so links can be followed locally — never use that on a
public gateway, since anyone with log access could take over accounts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str


class EmailSender(ABC):
    @abstractmethod
    async def send(self, email: Email) -> None: ...

    @property
    def delivers(self) -> bool:
        """Whether messages reach an inbox (False for the development log sender)."""
        return True


class SmtpEmailSender(EmailSender):
    def __init__(self) -> None:
        self._host = os.environ["RELAY_SMTP_HOST"]
        self._port = int(os.environ.get("RELAY_SMTP_PORT", "587"))
        self._username = os.environ.get("RELAY_SMTP_USERNAME", "")
        self._password = os.environ.get("RELAY_SMTP_PASSWORD", "")
        self._starttls = os.environ.get("RELAY_SMTP_STARTTLS", "1").lower() not in ("0", "false", "no")
        self._sender = os.environ.get("RELAY_EMAIL_FROM", "Relay <no-reply@localhost>")

    def _send_sync(self, email: Email) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._sender, email.to, email.subject
        message.set_content(email.text)
        with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(self._send_sync, email)


class LogEmailSender(EmailSender):
    async def send(self, email: Email) -> None:
        # The log handler redacts token=… values, so the whole message is printed separately.
        logger.warning("development email (no RELAY_SMTP_HOST) to=%s subject=%s", email.to, email.subject)
        print(f"\n----- email to {email.to}: {email.subject} -----\n{email.text}\n-----\n", flush=True)

    @property
    def delivers(self) -> bool:
        return False


def email_sender_from_env() -> EmailSender:
    return SmtpEmailSender() if os.environ.get("RELAY_SMTP_HOST") else LogEmailSender()
