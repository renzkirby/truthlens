import secrets

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone


def generate_email_verification_token():
    return secrets.token_urlsafe(32)


def build_email_verification_url(token):
    frontend_url = settings.FRONTEND_URL.rstrip("/")

    return (
        f"{frontend_url}/verify-email"
        f"?token={token}"
    )


def prepare_email_verification(user):
    profile = user.profile

    token = generate_email_verification_token()

    profile.email_verification_token = token
    profile.email_verification_sent_at = timezone.now()

    profile.save(
        update_fields=[
            "email_verification_token",
            "email_verification_sent_at",
        ]
    )

    return token


def send_email_verification(user):
    token = prepare_email_verification(user)
    verification_url = build_email_verification_url(token)
    expiry_hours = settings.EMAIL_VERIFICATION_TOKEN_LIFETIME_HOURS

    subject = "Verify your TruthLens email"
    text_body = (
        "Verify your email address\n\n"
        "Confirm this email address to secure your TruthLens account "
        "and continue to TruthLens.\n\n"
        "Verify your email:\n"
        f"{verification_url}\n\n"
        f"This verification link expires in {expiry_hours} hours.\n\n"
        "If you did not request this verification, you can safely ignore this email."
    )
    html_body = render_to_string(
        "emails/email_verification.html",
        {
            "verification_url": verification_url,
            "expiry_hours": expiry_hours,
        },
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")

    delivered_count = message.send(fail_silently=False)
    if delivered_count != 1:
        raise RuntimeError(
            "The email verification message was not accepted by the configured email backend."
        )

    return delivered_count
