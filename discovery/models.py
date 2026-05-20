from __future__ import annotations

import uuid

from django.db import models


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "사용자"
        ASSISTANT = "assistant", "어시스턴트"
        TOOL = "tool", "도구 결과"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True, default="")
    tool_name = models.CharField(max_length=64, blank=True, default="")
    tool_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]


class PipelineTrace(models.Model):
    class Kind(models.TextChoices):
        SEARCH = "search", "검색"
        INDEXING = "indexing", "색인"
        IMPORT = "import", "가져오기"

    class Status(models.TextChoices):
        OK = "ok", "성공"
        ERROR = "error", "오류"
        EMPTY = "empty", "결과 없음"

    id = models.UUIDField(primary_key=True, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_traces",
    )
    job_public_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    summary = models.CharField(max_length=512, blank=True, default="")
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
