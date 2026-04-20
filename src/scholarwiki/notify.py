from __future__ import annotations
import smtplib
import socket
from email.message import EmailMessage


def send_notification(
    to: str,
    subject: str,
    body: str,
    smtp_host: str = "localhost",
    smtp_port: int = 25,
    from_addr: str | None = None,
) -> None:
    """Send a plain-text email via the local SMTP relay. Raises on failure."""
    if from_addr is None:
        from_addr = f"scholarwiki@{socket.getfqdn()}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
        s.send_message(msg)
