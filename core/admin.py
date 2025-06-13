from django.contrib import admin
from . import models

# Register your models here.
admin.site.register(models.Place)
admin.site.register(models.Category)
admin.site.register(models.MenuItem)
admin.site.register(models.Order)
admin.site.register(models.Printer)
admin.site.register(models.Table)
