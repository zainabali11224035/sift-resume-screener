"""
mailer.py
---------
Thin email-sending helper used for notifications (new account created,
account locked out, screening batch finished, etc).

Configured entirely through environment variables so no secrets live in
the code:

    SIFT_SMTP_HOST      e.g. smtp.gmail.com
    SIFT_SMTP_PORT      e.g. 587
    SIFT_SMTP_USER      the mailbox that sends the emails
    SIFT_SMTP_PASSWORD  app password / SMTP password
    SIFT_FROM_EMAIL     "From" address shown to recipients (defaults to SIFT_SMTP_USER)
    SIFT_SMTP_USE_TLS   "1"/"0", defaults to "1"

If SIFT_SMTP_HOST / SIFT_SMTP_USER / SIFT_SMTP_PASSWORD aren't set, emails
are just printed to the console instead of sent. That keeps the app fully
usable on a machine (or a demo in front of your teacher) with no mail
server configured -- nothing crashes, you just won't get a real email.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage


def _smtp_configured():
    return bool(
        os.environ.get("SIFT_SMTP_HOST")
        and os.environ.get("SIFT_SMTP_USER")
        and os.environ.get("SIFT_SMTP_PASSWORD")
    )


def send_email(to_email, subject, body):
    """
    Best-effort email send. Returns True if a real email was sent, False
    if it fell back to console logging (or to_email was empty). Never
    raises -- a mail failure should never break the request that
    triggered it.
    """
    if not to_email:
        return False

    if not _smtp_configured():
        print(
            "\n[SIFT MAIL - not configured, printing instead]\n"
            f"To: {to_email}\nSubject: {subject}\n\n{body}\n"
            "[Set SIFT_SMTP_HOST / SIFT_SMTP_USER / SIFT_SMTP_PASSWORD to send real emails]\n"
        )
        return False

    host = os.environ.get("SIFT_SMTP_HOST")
    port = int(os.environ.get("SIFT_SMTP_PORT", "587"))
    user = os.environ.get("SIFT_SMTP_USER")
    password = os.environ.get("SIFT_SMTP_PASSWORD")
    from_email = os.environ.get("SIFT_FROM_EMAIL", user)
    use_tls = os.environ.get("SIFT_SMTP_USE_TLS", "1") != "0"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 -- a failed notification must not break the request
        print(f"[SIFT MAIL] Failed to send to {to_email}: {e}")
        return False


def notify_account_created(to_email, username, role):
    if not to_email:
        return
    send_email(
        to_email,
        "Your Sift account has been created",
        f"Hi {username},\n\n"
        f"An account was created for you on Sift ({role}).\n"
        "Log in and change your password from the Account page.\n\n"
        "— Sift",
    )


def notify_account_locked(to_email, username):
    if not to_email:
        return
    send_email(
        to_email,
        "Sift: your account was temporarily locked",
        f"Hi {username},\n\n"
        f"Your Sift account was locked for {os_lockout_minutes()} minutes after too many "
        "failed login attempts. If this wasn't you, please change your password once the "
        "lock clears.\n\n"
        "— Sift",
    )


def notify_screening_complete(to_email, username, job_title, candidate_count):
    if not to_email:
        return
    send_email(
        to_email,
        f"Sift: screening finished for '{job_title}'",
        f"Hi {username},\n\n"
        f"Your batch for '{job_title}' has finished screening "
        f"({candidate_count} candidate{'s' if candidate_count != 1 else ''} ranked).\n"
        "Log in to Sift to review the shortlist.\n\n"
        "— Sift",
    )


def os_lockout_minutes():
    # Kept local to avoid a circular import with database.py just for one constant.
    return os.environ.get("SIFT_LOCKOUT_MINUTES", "15")
