"""Tests for the quillmark integration seams: the MCP-result → PDF-artifact
bridge detection/metadata logic and the agentic tool-loop context framing."""

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from conversations.constants import ArtifactStatus, ArtifactType, SenderType
from conversations.models import Artifact, ArtifactGroup, Conversation, Message
from mcp.services.artifact_bridge import (
    _detect_pdf_url,
    _extract_document_meta,
    _find_existing_artifact,
)
from mcp.services.tool_result_context import tool_result_context_builder

User = get_user_model()


class DetectPdfUrlTests(SimpleTestCase):
    def test_structured_content_pdf(self):
        result = {
            "structuredContent": {
                "url": "http://quillmark-mcp:8080/artifacts/a.pdf",
                "mimeType": "application/pdf",
            }
        }
        self.assertEqual(
            _detect_pdf_url(result), "http://quillmark-mcp:8080/artifacts/a.pdf"
        )

    def test_resource_link_fallback(self):
        result = {
            "content": [
                {"type": "text", "text": "rendered"},
                {
                    "type": "resource_link",
                    "uri": "http://quillmark-mcp:8080/artifacts/b.pdf",
                    "mimeType": "application/pdf",
                },
            ]
        }
        self.assertEqual(
            _detect_pdf_url(result), "http://quillmark-mcp:8080/artifacts/b.pdf"
        )

    def test_non_pdf_and_malformed_results_ignored(self):
        self.assertIsNone(_detect_pdf_url(None))
        self.assertIsNone(_detect_pdf_url("plain text"))
        self.assertIsNone(_detect_pdf_url({"content": [{"type": "text", "text": "x"}]}))
        self.assertIsNone(
            _detect_pdf_url(
                {"structuredContent": {"url": "http://x/a.png", "mimeType": "image/png"}}
            )
        )


class ExtractDocumentMetaTests(SimpleTestCase):
    def test_subject_and_quill_extracted(self):
        content = (
            "~~~card-yaml\n$quill: cmu_memo@0.1.0\n$kind: main\n"
            "subject: FY27 Funding Request\n~~~\n\nBody."
        )
        meta = _extract_document_meta({"content": content})
        self.assertEqual(meta["quill"], "cmu_memo@0.1.0")
        self.assertEqual(meta["title"], "FY27 Funding Request")

    def test_headline_used_for_onepager(self):
        content = (
            "~~~card-yaml\n$quill: cmu_onepager@0.1.0\n$kind: main\n"
            "headline: DARE: The Case for FY27\n~~~\nBody"
        )
        meta = _extract_document_meta({"content": content})
        self.assertEqual(meta["title"], "DARE: The Case for FY27")

    def test_legacy_frontmatter_still_parsed(self):
        content = (
            "---\nQUILL: cmu_memo@0.1.0\nsubject: FY27 Funding Request\n---\n\nBody."
        )
        meta = _extract_document_meta({"content": content})
        self.assertEqual(meta["quill"], "cmu_memo@0.1.0")
        self.assertEqual(meta["title"], "FY27 Funding Request")

    def test_fallback_title(self):
        meta = _extract_document_meta({"content": "no frontmatter here"})
        self.assertEqual(meta["title"], "CMU Document")
        self.assertEqual(meta["quill"], "")


class ToolResultContextTests(SimpleTestCase):
    RESULTS = [{"tool_name": "quillmark__create_document", "result": "diag: bad field"}]

    def test_final_round_forbids_tools(self):
        text = tool_result_context_builder.build(self.RESULTS, final=True)
        self.assertIn("Do not call additional tools", text)
        self.assertIn("quillmark__create_document", text)

    def test_continuing_round_demands_retry(self):
        text = tool_result_context_builder.build(self.RESULTS, final=False)
        self.assertIn("CALL THE TOOL AGAIN", text)
        self.assertNotIn("Do not call additional tools", text)

    def test_default_is_final(self):
        self.assertIn(
            "Do not call additional tools",
            tool_result_context_builder.build(self.RESULTS),
        )


class FindExistingArtifactRegenerateTests(TestCase):
    """Regression test for the "artifact one step behind" bug: regenerating
    a document reuses the same Message row, so excluding by message (the old
    behavior) hid the artifact a regenerate is meant to version, forking a
    disconnected group instead. Exclusion is now by an explicit per-turn id
    set instead."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="quill-user@example.com", password="pw"
        )
        self.conversation = Conversation.active_objects.create(user=self.user)
        self.message = Message.active_objects.create(
            conversation=self.conversation,
            sender_type=SenderType.AI_ASSISTANT,
            message="",
        )
        self.group = ArtifactGroup.active_objects.create(
            conversation=self.conversation, base_title="FY27 Memo"
        )
        self.artifact_v1 = Artifact.active_objects.create(
            conversation=self.conversation,
            message=self.message,
            artifact_group=self.group,
            title="FY27 Memo",
            content="v1",
            artifact_type=ArtifactType.PDF,
            filename="fy27-memo.pdf",
            content_type="application/pdf",
            source_tool="quillmark__create_document",
            status=ArtifactStatus.COMPLETED,
            metadata={"quill": "cmu_memo@0.1.0"},
            version=1,
        )
        self.group.latest_version = self.artifact_v1
        self.group.save(update_fields=["latest_version"])

    def test_regenerate_on_same_message_finds_prior_version(self):
        # Regenerate reuses the same Message row and starts a fresh turn, so
        # bridged_artifact_ids is empty — v1 must still be found so it gets
        # versioned instead of forking a new group.
        found = async_to_sync(_find_existing_artifact)(
            self.conversation,
            "quillmark__create_document",
            "cmu_memo@0.1.0",
            "FY27 Memo",
            set(),
        )
        self.assertEqual(found, self.artifact_v1)

    def test_same_turn_rerender_does_not_match_its_own_output(self):
        # Once v1 has already been (re)bridged earlier in this turn, it must
        # be excluded so a later render in the same turn doesn't clobber it.
        found = async_to_sync(_find_existing_artifact)(
            self.conversation,
            "quillmark__create_document",
            "cmu_memo@0.1.0",
            "FY27 Memo",
            {self.artifact_v1.id},
        )
        self.assertIsNone(found)

    def test_chained_versions_keep_source_tool_and_increment(self):
        # Regression for the "always previews the first document" bug:
        # create_new_version() previously dropped source_tool/content_type,
        # so every later _find_existing_artifact lookup (which filters on
        # source_tool) fell through to the original v1 row instead of the
        # true latest — collapsing every subsequent version to "v2" forever.
        v2 = self.artifact_v1.create_new_version()
        v2.message = self.message
        v2.content = "v2"
        v2.save(update_fields=["message", "content"])

        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.source_tool, "quillmark__create_document")
        self.assertEqual(v2.content_type, "application/pdf")

        found = async_to_sync(_find_existing_artifact)(
            self.conversation,
            "quillmark__create_document",
            "cmu_memo@0.1.0",
            "FY27 Memo",
            set(),
        )
        self.assertEqual(found, v2)

        v3 = found.create_new_version()
        self.assertEqual(v3.version, 3)
        self.assertEqual(v3.source_tool, "quillmark__create_document")
