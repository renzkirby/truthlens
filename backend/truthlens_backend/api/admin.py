from django.contrib import admin
from .models import ThreadComment, UserProfile, Claim, Thread, EvidenceSubmission, Vote

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(Claim)
admin.site.register(Thread)
admin.site.register(EvidenceSubmission)
admin.site.register(Vote)
admin.site.register(ThreadComment)
