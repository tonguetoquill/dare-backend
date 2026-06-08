from django.contrib import admin

from research.models import ResearchProject


@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "question", "field")
    raw_id_fields = ("user",)
