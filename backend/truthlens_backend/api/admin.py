from django.contrib import admin
from .models import (
    ThreadComment,
    ThreadFlag,
    UserProfile,
    Claim,
    Thread,
    EvidenceSubmission,
    Vote,
    Organization,
    OrganizationMembership,
    VerificationAssignment,
)

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(Claim)
admin.site.register(Thread)
admin.site.register(EvidenceSubmission)
admin.site.register(Vote)
admin.site.register(ThreadComment)
admin.site.register(ThreadFlag)
admin.site.register(Organization)
admin.site.register(OrganizationMembership)
admin.site.register(VerificationAssignment)
