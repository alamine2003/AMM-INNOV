from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "channel", "title", "created_at", "sent_at", "read_at")
    list_filter = ("channel",)
    search_fields = ("title", "user__email")
