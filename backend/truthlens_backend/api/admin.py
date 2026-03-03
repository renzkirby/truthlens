from django.contrib import admin
from .models import UserProfile, Claim, Thread, EvidenceSubmission, Vote

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(Claim)
admin.site.register(Thread)
admin.site.register(EvidenceSubmission)
admin.site.register(Vote)
