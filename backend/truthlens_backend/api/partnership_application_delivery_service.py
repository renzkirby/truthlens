import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import PartnershipApplication

logger = logging.getLogger(__name__)


def send_partnership_application_rejection_email(application_id):
    application = (
        PartnershipApplication.objects.select_related("organization")
        .filter(pk=application_id)
        .first()
    )
    if application is None:
        logger.warning(
            "Partnership application rejection email skipped because application=%s was not found.",
            application_id,
        )
        return 0

    if application.status != PartnershipApplication.Status.REJECTED:
        logger.warning(
            "Partnership application rejection email skipped because application=%s is status=%s.",
            application_id,
            application.status,
        )
        return 0

    recipient = (application.applicant_email or "").strip()
    if not recipient:
        logger.warning(
            "Partnership application rejection email skipped because application=%s has no applicant email.",
            application_id,
        )
        return 0

    organization_name = application.organization.name
    decision_notes = (application.decision_notes or "").strip()

    subject = f"TruthLens partnership application update - {organization_name}"
    text_body = (
        f"Hello {application.applicant_full_name},\n\n"
        f"Thank you for applying for {organization_name} to become a TruthLens Partner Organization.\n\n"
        "After review, TruthLens is unable to approve this partnership application at this time.\n\n"
        "Decision rationale:\n"
        f"{decision_notes}\n\n"
        "This decision applies to the submitted partnership application and does not affect any personal TruthLens account you may have.\n\n"
        "TruthLens"
    )

    html_body = render_to_string(
        "emails/partnership_application_rejected.html",
        {
            "applicant_name": application.applicant_full_name,
            "organization_name": organization_name,
            "decision_notes": decision_notes,
        },
    )

    message = EmailMultiAlternatives(
        subject=subject.replace("\r", " ").replace("\n", " "),
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")

    delivered_count = message.send(fail_silently=False)
    if delivered_count != 1:
        raise RuntimeError(
            "The partnership application rejection email was not accepted by the configured email backend."
        )
    return delivered_count


def dispatch_partnership_application_rejection_email(application_id):
    try:
        return send_partnership_application_rejection_email(application_id)
    except Exception:
        logger.exception(
            "Partnership application rejection email delivery failed for application=%s.",
            application_id,
        )
        return 0
