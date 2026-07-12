"""Tests for the quillmark integration seams: the MCP-result → PDF-artifact
bridge detection/metadata logic and the agentic tool-loop context framing."""

from django.test import SimpleTestCase

from mcp.services.artifact_bridge import _detect_pdf_url, _extract_document_meta
from mcp.services.tool_result_context import tool_result_context_builder


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
            "---\nQUILL: cmu_memo@0.1.0\nsubject: FY27 Funding Request\n---\n\nBody."
        )
        meta = _extract_document_meta({"content": content})
        self.assertEqual(meta["quill"], "cmu_memo@0.1.0")
        self.assertEqual(meta["title"], "FY27 Funding Request")

    def test_headline_used_for_onepager(self):
        content = "---\nQUILL: cmu_onepager@0.1.0\nheadline: DARE: The Case for FY27\n---\nBody"
        meta = _extract_document_meta({"content": content})
        self.assertEqual(meta["title"], "DARE: The Case for FY27")

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
