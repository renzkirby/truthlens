from copy import deepcopy

from django.test import SimpleTestCase

from api.rich_text_schema import (
    PROFILE_COMMENT,
    PROFILE_DISCUSSION,
    PROFILE_PUBLICATION,
    RichTextSchemaError,
    normalize_rich_text_with_plain,
    plain_text_to_rich_text,
    rich_text_to_plain,
    validate_rich_text_document,
)


class RichTextSchemaTests(SimpleTestCase):
    def rich_document(self):
        return {
            "schema_version": 1,
            "doc": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Evidence-based ",
                                "marks": [{"type": "bold"}],
                            },
                            {
                                "type": "text",
                                "text": "analysis",
                                "marks": [
                                    {
                                        "type": "link",
                                        "attrs": {
                                            "href": "https://example.com/source",
                                            "target": "_blank",
                                            "rel": "noopener",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "First source"}
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        }

    def test_discussion_document_is_canonicalized_and_projected(self):
        value = self.rich_document()

        normalized, plain = normalize_rich_text_with_plain(
            value,
            profile=PROFILE_DISCUSSION,
        )

        self.assertEqual(
            normalized["doc"]["content"][0]["content"][1]["marks"],
            [
                {
                    "type": "link",
                    "attrs": {"href": "https://example.com/source"},
                }
            ],
        )
        self.assertEqual(
            plain,
            "Evidence-based analysis\n\n- First source",
        )

    def test_plain_text_round_trip_preserves_paragraphs_and_hard_breaks(self):
        value = plain_text_to_rich_text("First line\nSecond line\n\nNext paragraph")

        self.assertEqual(
            rich_text_to_plain(value, profile=PROFILE_DISCUSSION),
            "First line\nSecond line\n\nNext paragraph",
        )

    def test_unsafe_and_relative_links_are_rejected(self):
        for href in (
            "javascript:alert(1)",
            "data:text/html,test",
            "/relative/path",
        ):
            value = self.rich_document()
            value["doc"]["content"][0]["content"][1]["marks"][0]["attrs"]["href"] = href

            with self.subTest(href=href), self.assertRaises(RichTextSchemaError):
                validate_rich_text_document(
                    value,
                    profile=PROFILE_DISCUSSION,
                )

    def test_unsupported_nodes_marks_and_envelope_fields_are_rejected(self):
        image = self.rich_document()
        image["doc"]["content"].append(
            {"type": "image", "attrs": {"src": "https://example.com/image.png"}}
        )
        with self.assertRaises(RichTextSchemaError):
            validate_rich_text_document(image, profile=PROFILE_DISCUSSION)

        strike = self.rich_document()
        strike["doc"]["content"][0]["content"][0]["marks"] = [{"type": "strike"}]
        with self.assertRaises(RichTextSchemaError):
            validate_rich_text_document(strike, profile=PROFILE_DISCUSSION)

        extra = self.rich_document()
        extra["html"] = "<script>alert(1)</script>"
        with self.assertRaises(RichTextSchemaError):
            validate_rich_text_document(extra, profile=PROFILE_DISCUSSION)

    def test_comment_profile_rejects_ordered_lists(self):
        value = self.rich_document()
        value["doc"]["content"][1]["type"] = "orderedList"
        value["doc"]["content"][1]["attrs"] = {"start": 1}

        with self.assertRaises(RichTextSchemaError):
            validate_rich_text_document(value, profile=PROFILE_COMMENT)

    def test_publication_profile_accepts_h2_h3_and_underline(self):
        value = {
            "schema_version": 1,
            "doc": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 2},
                        "content": [{"type": "text", "text": "What we found"}],
                    },
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Important context",
                                "marks": [{"type": "underline"}],
                            }
                        ],
                    },
                    {
                        "type": "heading",
                        "attrs": {"level": 3},
                        "content": [{"type": "text", "text": "Source review"}],
                    },
                ],
            },
        }

        normalized = validate_rich_text_document(
            value,
            profile=PROFILE_PUBLICATION,
        )

        self.assertEqual(normalized, value)
        self.assertEqual(
            rich_text_to_plain(value, profile=PROFILE_PUBLICATION),
            "What we found\n\nImportant context\n\nSource review",
        )

    def test_publication_profile_rejects_h1_and_text_limit_overflow(self):
        heading = {
            "schema_version": 1,
            "doc": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "Not allowed"}],
                    }
                ],
            },
        }
        with self.assertRaises(RichTextSchemaError):
            validate_rich_text_document(heading, profile=PROFILE_PUBLICATION)

        oversized = {
            "schema_version": 1,
            "doc": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "x" * 50001}],
                    }
                ],
            },
        }
        with self.assertRaises(RichTextSchemaError):
            validate_rich_text_document(
                oversized,
                profile=PROFILE_PUBLICATION,
            )

    def test_input_is_not_mutated_during_normalization(self):
        original = self.rich_document()
        before = deepcopy(original)

        validate_rich_text_document(
            original,
            profile=PROFILE_DISCUSSION,
        )

        self.assertEqual(original, before)
