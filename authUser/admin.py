from django.contrib import admin
from .models import User
# Register your models here.

class UsersAdmin(admin.ModelAdmin):
    list_display = (
        "user_name",
        "phone_number",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
        "date_joined",
        "last_login",
    )

admin.site.register(User,UsersAdmin)