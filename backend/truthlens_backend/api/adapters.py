from django.contrib.auth import get_user_model
from django.utils.text import slugify
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


User = get_user_model()


def generate_unique_username(display_name="", email=""):
    """
    Generate a readable, unique TruthLens username.

    Examples:
        "John Smith" -> john_smith
        collision    -> john_smith2
    """
    source = display_name.strip()

    if not source and email:
        source = email.split("@")[0]

    base = slugify(source).replace("-", "_")

    if not base:
        base = "truthlens_user"

    # Django's default User.username max_length is 150.
    base = base[:140]

    username = base
    counter = 2

    while User.objects.filter(username__iexact=username).exists():
        suffix = str(counter)

        username = (
            f"{base[:150 - len(suffix)]}"
            f"{suffix}"
        )

        counter += 1

    return username


class TruthLensSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Initializes a TruthLens profile from a social provider
    only when a brand-new social account is being created.

    Existing TruthLens profiles are not overwritten.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(
            request,
            sociallogin,
            data,
        )

        extra_data = sociallogin.account.extra_data or {}

        email = (
            data.get("email")
            or extra_data.get("email")
            or ""
        )

        first_name = (
            data.get("first_name")
            or extra_data.get("given_name")
            or ""
        ).strip()

        last_name = (
            data.get("last_name")
            or extra_data.get("family_name")
            or ""
        ).strip()

        display_name = (
            extra_data.get("name")
            or f"{first_name} {last_name}".strip()
        )

        user.email = email
        user.first_name = first_name
        user.last_name = last_name

        user.username = generate_unique_username(
            display_name=display_name,
            email=email,
        )

        return user

    def save_user(
        self,
        request,
        sociallogin,
        form=None,
    ):
        user = super().save_user(
            request,
            sociallogin,
            form,
        )

        extra_data = sociallogin.account.extra_data or {}
        avatar_url = extra_data.get("picture")

        profile = user.profile

        update_fields = []

        # This is account initialization, so importing the
        # Google avatar here is safe.
        if avatar_url and not profile.avatar_url:
            profile.avatar_url = avatar_url
            update_fields.append("avatar_url")

        # Don't blindly trust every future social provider.
        # Use allauth's verified-email information.
        email_verified = any(
            email_address.verified
            and email_address.email.lower()
            == user.email.lower()
            for email_address in sociallogin.email_addresses
        )

        if email_verified and not profile.is_email_verified:
            profile.is_email_verified = True
            update_fields.append("is_email_verified")

        if update_fields:
            profile.save(update_fields=update_fields)

        return user