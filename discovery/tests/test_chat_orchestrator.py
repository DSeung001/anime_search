from __future__ import annotations

import uuid

from django.test import TestCase

from discovery.models import ChatMessage, ChatSession
from discovery.services.chat_orchestrator import (
    ChatSessionNotFoundError,
    _build_user_prompt,
    _format_chat_prompt,
    _merge_scene_lists,
    get_or_create_session,
)


class FormatChatPromptTests(TestCase):
    def test_no_history_returns_message_only(self) -> None:
        self.assertEqual(_format_chat_prompt([], "안녕"), "안녕")

    def test_with_history_includes_current_once(self) -> None:
        prompt = _format_chat_prompt(["사용자: 이전", "어시스턴트: 네"], "지금")
        self.assertIn("이전 대화:", prompt)
        self.assertIn("사용자: 이전", prompt)
        self.assertIn("현재 사용자 메시지: 지금", prompt)
        self.assertEqual(prompt.count("지금"), 1)


class BuildUserPromptTests(TestCase):
    def test_empty_session(self) -> None:
        session = ChatSession.objects.create()
        self.assertEqual(_build_user_prompt(session, "첫 메시지"), "첫 메시지")

    def test_prior_dialogue_only(self) -> None:
        session = ChatSession.objects.create()
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.USER, content="3화 싸움"
        )
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.ASSISTANT, content="찾아볼게요"
        )
        prompt = _build_user_prompt(session, "다른 각도")
        self.assertIn("사용자: 3화 싸움", prompt)
        self.assertIn("어시스턴트: 찾아볼게요", prompt)
        self.assertIn("현재 사용자 메시지: 다른 각도", prompt)
        self.assertNotIn("현재 사용자 메시지: 3화 싸움", prompt)

    def test_tool_messages_do_not_consume_history_slots(self) -> None:
        session = ChatSession.objects.create()
        for _ in range(10):
            ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.TOOL,
                content='{"scenes": []}',
                tool_name="search_scenes",
            )
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.USER, content="유지되는 사용자"
        )
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.ASSISTANT, content="유지되는 답변"
        )
        prompt = _build_user_prompt(session, "새 질문")
        self.assertIn("유지되는 사용자", prompt)
        self.assertIn("유지되는 답변", prompt)
        self.assertNotIn('{"scenes"', prompt)


class MergeSceneListsTests(TestCase):
    def test_dedupes_by_job_and_peak_keeps_higher_score(self) -> None:
        job = str(uuid.uuid4())
        low = {
            "job_public_id": job,
            "peak_sec": 10.0,
            "score": 0.5,
        }
        high = {
            "job_public_id": job,
            "peak_sec": 10.0,
            "score": 0.9,
        }
        merged = _merge_scene_lists([low], [high])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["score"], 0.9)

    def test_sorts_by_score_desc(self) -> None:
        a = {"job_public_id": "a", "peak_sec": 1.0, "score": 0.3}
        b = {"job_public_id": "b", "peak_sec": 2.0, "score": 0.8}
        merged = _merge_scene_lists([], [a, b])
        self.assertEqual(merged[0]["job_public_id"], "b")


class GetOrCreateSessionTests(TestCase):
    def test_creates_when_no_id(self) -> None:
        session = get_or_create_session(None)
        self.assertIsNotNone(session.id)

    def test_returns_existing(self) -> None:
        existing = ChatSession.objects.create()
        found = get_or_create_session(existing.id)
        self.assertEqual(found.id, existing.id)

    def test_raises_when_missing(self) -> None:
        with self.assertRaises(ChatSessionNotFoundError):
            get_or_create_session(uuid.uuid4())
