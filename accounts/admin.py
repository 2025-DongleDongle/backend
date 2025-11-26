from django.contrib import admin
from .models import *

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    model = User
    list_display = ("id", "nickname")

admin.site.register(University)
admin.site.register(ExchangeUniversity)
admin.site.register(ExchangeProfile)
