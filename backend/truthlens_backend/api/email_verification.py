import secrets

from django.conf import settings
from django.core.mail import send_mail
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

    send_mail(
        subject="Verify your TruthLens email",
        message=(
            "Thanks for creating a TruthLens account.\n\n"
            "Verify your email address using this link:\n"
            f"{verification_url}\n\n"
            "If you did not create this account, "
            "you can ignore this message."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )