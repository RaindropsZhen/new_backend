from django.apps import AppConfig
from django.conf import settings
import os 

class AuthuserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'authUser'
    path = os.path.join(settings.BASE_DIR, 'authUser')