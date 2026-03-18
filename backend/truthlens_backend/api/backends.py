from django.contrib.auth.models import User
from django.contrib.auth.backends import ModelBackend

class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username = None, password = None, **kwargs):
        try:
            user = User.objects.filter(username=username).first() or \
                   User.objects.filter(email=username).first()
            if user and user.check_password(password):
                return user
        except Exception:
            return None