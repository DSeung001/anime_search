from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from discovery.models import ChatMessage, ChatSession, PipelineTrace


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "tool_name", "created_at")


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "updated_at")
    inlines = [ChatMessageInline]


@admin.register(PipelineTrace)
class PipelineTraceAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "summary", "session", "job_public_id", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("id", "summary", "session_id", "job_public_id")
    readonly_fields = ("id", "kind", "session", "job_public_id", "status", "summary", "payload", "created_at", "web_link")
    ordering = ("-created_at",)

    @admin.display(description="웹 상세")
    def web_link(self, obj: PipelineTrace) -> str:
        url = reverse("discovery_trace_detail", kwargs={"trace_id": obj.id})
        return format_html('<a href="{}">/search/traces/…</a>', url)
