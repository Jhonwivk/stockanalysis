#!/usr/bin/env python3
"""Send a market review file (md/pdf/txt) via SMTP.

Reads credentials from environment or .env in repo root (not committed).
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def send(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    mail_from: str,
    mail_to: list[str],
    subject: str,
    body: str,
    attachments: list[Path],
    use_ssl: bool = True,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)
    msg.set_content(body)

    for path in attachments:
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(user, password)
            smtp.send_message(msg)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")

    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="附件路径（md/pdf 等）")
    ap.add_argument("--subject", default="")
    ap.add_argument("--body", default="")
    args = ap.parse_args()

    host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    mail_to = [x.strip() for x in os.environ["EMAIL_TO"].split(",") if x.strip()]
    mail_from = os.environ.get("EMAIL_FROM") or user
    name = os.environ.get("EMAIL_FROM_NAME", "A股盘面复盘")
    if name:
        mail_from = f"{name} <{mail_from}>"
    use_ssl = os.environ.get("SMTP_SSL", "true").lower() in ("1", "true", "yes")

    paths = [Path(p) for p in args.files]
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing file: {p}")

    subject = args.subject or f"A股盘面复盘 {paths[0].stem}"
    body = args.body or "附件为当日盘面复盘（自动发送）。仅供研究，不构成投资建议。"

    send(
        host=host,
        port=port,
        user=user,
        password=password,
        mail_from=mail_from,
        mail_to=mail_to,
        subject=subject,
        body=body,
        attachments=paths,
        use_ssl=use_ssl,
    )
    print(f"sent to {mail_to}: {[p.name for p in paths]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
