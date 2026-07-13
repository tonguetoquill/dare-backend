from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from conversations.constants import SenderType
from conversations.models import Conversation, Message

# Create your tests here.


class SanitizeTitleTests(SimpleTestCase):
    """Model-generated conversation titles must fit the 255-char column and
    read like titles (small models return markdown headers or paragraphs)."""

    def test_markdown_and_quotes_stripped(self):
        from core.services.conversation_service import ConversationService

        self.assertEqual(
            ConversationService._sanitize_title('# "Claude AI Overview"'),
            "Claude AI Overview",
        )

    def test_multiline_reply_takes_first_line(self):
        from core.services.conversation_service import ConversationService

        raw = "Funding Memo Discussion\n\nThis conversation covers..."
        self.assertEqual(
            ConversationService._sanitize_title(raw), "Funding Memo Discussion"
        )

    def test_long_reply_truncated_under_column_limit(self):
        from core.services.conversation_service import ConversationService

        title = ConversationService._sanitize_title("word " * 100)
        self.assertLessEqual(len(title), 120)
        self.assertTrue(title.endswith("…"))

    def test_empty_falls_back(self):
        from core.services.conversation_service import ConversationService

        self.assertEqual(ConversationService._sanitize_title(""), "New Chat")
        self.assertEqual(ConversationService._sanitize_title("###"), "New Chat")


class ConversationHistorySkipRecentTests(TestCase):
    """Regression test for the "quillmark generates the previous message's
    document" bug.

    ``build_standard_messages`` re-appends the current turn's content itself
    as ``request.message``, so ``get_conversation_history``'s default
    ``skip_recent=2`` drops the current-turn user row (plus the in-progress
    AI row) to avoid duplicating it. That assumption breaks in the MCP tool
    loop's follow-up rounds (``MCPToolHandler.stream_tool_result_response``),
    where ``request.message`` is a tool-result summary, not the user's
    actual request — those rounds pass ``skip_recent=1`` so the real
    current-turn message stays in history instead of silently vanishing.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="hist-user@example.com", password="pw"
        )
        self.conversation = Conversation.active_objects.create(user=self.user)

        Message.active_objects.create(
            conversation=self.conversation,
            sender_type=SenderType.PLAYER,
            message="What's the capital of France?",
        )
        Message.active_objects.create(
            conversation=self.conversation,
            sender_type=SenderType.AI_ASSISTANT,
            message="Paris.",
        )
        # Current turn: real user request, then the still-empty AI
        # placeholder created before streaming begins.
        Message.active_objects.create(
            conversation=self.conversation,
            sender_type=SenderType.PLAYER,
            message="Generate a memo about the Q3 budget.",
        )
        Message.active_objects.create(
            conversation=self.conversation,
            sender_type=SenderType.AI_ASSISTANT,
            message="",
        )

    def test_default_skip_recent_drops_current_user_message(self):
        from core.services.llm_helpers.db_helpers import (
            _get_conversation_history_sync,
        )

        history = _get_conversation_history_sync(self.conversation, limit=20)
        contents = [m["content"] for m in history]

        self.assertNotIn("Generate a memo about the Q3 budget.", contents)
        self.assertIn("What's the capital of France?", contents)

    def test_skip_recent_one_keeps_current_user_message(self):
        from core.services.llm_helpers.db_helpers import (
            _get_conversation_history_sync,
        )

        history = _get_conversation_history_sync(
            self.conversation, limit=20, skip_recent=1
        )
        contents = [m["content"] for m in history]

        self.assertIn("Generate a memo about the Q3 budget.", contents)
        self.assertIn("What's the capital of France?", contents)
