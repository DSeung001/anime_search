from __future__ import annotations

import json
import uuid

from django.test import Client, TestCase
from django.urls import reverse

from discovery.models import ChatMessage, ChatSession
from discovery.services.chat_history import get_session_messages, list_recent_sessions


class ChatHistoryServiceTests(TestCase):
    def test_list_recent_sessions_preview(self) -> None:
        session = ChatSession.objects.create()
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.USER, content="3화 싸움 장면"
        )
        rows = list_recent_sessions(limit=10)
        self.assertEqual(len(rows), 1)
        self.assertIn("3화 싸움", rows[0]["preview"])

    def test_get_session_messages_includes_assistant(self) -> None:
        session = ChatSession.objects.create()
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.USER, content="질문"
        )
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.ASSISTANT, content="답변"
        )
        payload = get_session_messages(session.id)
        roles = [m["role"] for m in payload["messages"]]
        self.assertEqual(roles, ["user", "assistant"])

    def test_get_session_messages_last_scenes(self) -> None:
        session = ChatSession.objects.create()
        scenes = [{"job_public_id": "x", "peak_sec": 1.0, "score": 0.5}]
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.TOOL,
            content="{}",
            tool_name="search_scenes",
            tool_payload={"scenes": scenes, "search_query_ko": "싸움"},
        )
        payload = get_session_messages(session.id)
        self.assertEqual(payload["last_scenes"], scenes)
        self.assertEqual(len(payload["messages"]), 1)


class ChatHistoryApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_home_page_lists_sessions(self) -> None:
        session = ChatSession.objects.create()
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.USER, content="테스트 대화"
        )
        resp = self.client.get(reverse("discovery_home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "테스트 대화")

    def test_sessions_api(self) -> None:
        ChatSession.objects.create()
        resp = self.client.get(reverse("discovery_sessions_api"))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(len(data["sessions"]), 1)

    def test_messages_api_404(self) -> None:
        resp = self.client.get(
            reverse("discovery_session_messages_api", kwargs={"session_id": uuid.uuid4()})
        )
        self.assertEqual(resp.status_code, 404)

    def test_chat_session_page_404(self) -> None:
        resp = self.client.get(
            reverse("discovery_chat_session", kwargs={"session_id": uuid.uuid4()})
        )
        self.assertEqual(resp.status_code, 404)
