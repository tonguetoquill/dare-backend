from django.contrib import admin

from research.models import (
    ResearchAgentRun,
    ResearchAgentToolCall,
    ResearchProject,
    ResearchSession,
    ResearchSource,
)


@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "question", "field")
    raw_id_fields = ("user",)


@admin.register(ResearchSession)
class ResearchSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "user", "mode", "status", "created_at")
    list_filter = ("mode", "status")
    raw_id_fields = ("project", "user")


class ResearchAgentToolCallInline(admin.TabularInline):
    model = ResearchAgentToolCall
    extra = 0


@admin.register(ResearchAgentRun)
class ResearchAgentRunAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "role", "mode", "status", "created_at")
    list_filter = ("mode", "status", "role")
    search_fields = ("task",)
    raw_id_fields = ("session", "project", "user")
    inlines = [ResearchAgentToolCallInline]


@admin.register(ResearchAgentToolCall)
class ResearchAgentToolCallAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "tool", "status", "duration_ms", "created_at")
    list_filter = ("status", "tool")
    raw_id_fields = ("run",)


@admin.register(ResearchSource)
class ResearchSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "name", "kind", "source_type", "created_at")
    list_filter = ("source_type",)
    search_fields = ("name", "title", "authors")
    raw_id_fields = ("project", "added_by")
