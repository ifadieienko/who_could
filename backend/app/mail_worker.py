"""Run as `python -m app.mail_worker --once` from cron, or without --once as a worker."""

import argparse
import os
import smtplib
import time
from email.message import EmailMessage
from datetime import timedelta
from sqlalchemy import select
from .database import db
from .repair_access import utc
from .repair_models import Outbox


def deliver_once():
    if not os.getenv("SMTP_HOST") or not os.getenv("SMTP_FROM"):
        return 0
    sent = 0
    for _ in range(50):
        with db() as s:
            m = s.scalar(
                select(Outbox)
                .where(
                    Outbox.status == "pending",
                    Outbox.next_attempt <= utc(),
                    Outbox.attempts < 5,
                )
                .order_by(Outbox.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if not m:
                break
            m.attempts += 1
            message = EmailMessage()
            message["From"] = os.environ["SMTP_FROM"]
            message["To"] = m.recipient
            message["Subject"] = m.subject
            message["Message-ID"] = (
                f'<who-could-{m.id}@{os.getenv("SMTP_MESSAGE_DOMAIN","localhost")}>'
            )
            message.set_content(m.body)
            try:
                with smtplib.SMTP(
                    os.environ["SMTP_HOST"],
                    int(os.getenv("SMTP_PORT", "587")),
                    timeout=20,
                ) as smtp:
                    if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
                        smtp.starttls()
                    if os.getenv("SMTP_USER"):
                        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                    smtp.send_message(message)
                m.status = "sent"
                m.last_error = None
                sent += 1
            except (OSError, smtplib.SMTPException) as exc:
                m.last_error = type(exc).__name__
                m.next_attempt = utc() + timedelta(minutes=2**m.attempts)
                if m.attempts >= 5:
                    m.status = "failed"
    return sent


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    while True:
        deliver_once()
        if args.once:
            break
        time.sleep(30)
