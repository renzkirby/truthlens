"""No-provider URL article-content selection regression cases."""
from django.test import SimpleTestCase
from api.services import clean_extracted_text


class URLArticleContextTests(SimpleTestCase):
    def test_nav_heavy_article_retains_body_beyond_old_cut(self):
        menu = "Apple Media Helpline media.help@apple.com " * 110
        raw = (
            "# Apple Reinvents the Phone with iPhone\n"
            "## Press Contacts\n" + menu + "\n"
            "## Shop and Learn\n" + "iPhone iPad Mac Account Store " * 120
            + "\n## About Apple\nApple press resources, contacts and site links.\n"
            + "## Introduction\nJanuary 9, 2007\n"
            + "Apple today introduced the original iPhone in January 2007, "
            "and announced that U.S. availability was planned for June 2007.\n"
        )
        self.assertGreater(raw.index("Apple today introduced"), 3000)
        clean = clean_extracted_text(raw)
        self.assertIn("Apple today introduced", clean)
        self.assertIn("planned for June 2007", clean)
        self.assertIn("January 9, 2007", clean)
        self.assertNotIn("media.help@apple.com", clean)
        self.assertNotIn("Shop and Learn", clean)

    def test_navigation_only_does_not_invent_claim(self):
        raw = (
            "# Apple Reinvents the Phone with iPhone "
            "## Press Contacts Apple Media Helpline media.help@apple.com "
            "## Shop and Learn iPhone iPad Mac "
            "## Account Sign In Wallet Store "
            "## About Apple Apple Media Helpline"
        )
        self.assertEqual(clean_extracted_text(raw), "")

    def test_short_public_claim_survives(self):
        self.assertEqual(clean_extracted_text("Earth is flat."), "Earth is flat.")

    def test_mixed_heading_and_navigation_on_one_line(self):
        raw = (
            "# Public Update ## Press Contacts Apple Media Helpline "
            "media.help@apple.com The latest updates, direct from Apple. "
            "## Shop and Learn Account iPhone iPad "
            "## Story The council confirmed on October 19, 2026 "
            "that planned road closures would not proceed."
        )
        result = clean_extracted_text(raw)
        self.assertIn("planned road closures would not proceed", result)
        self.assertNotIn("media.help@", result)
        self.assertNotIn("Shop and Learn", result)

    def test_multiline_article_paragraph_is_joined_without_losing_modality(self):
        raw = (
            "# Council Update\n"
            "The council announced that road works\n"
            "were only planned, not approved,\n"
            "for October 19, 2026.\n"
        )
        clean = clean_extracted_text(raw)
        self.assertIn("were only planned, not approved", clean)
        self.assertIn("for October 19, 2026.", clean)

    def test_short_full_sentence_is_preserved(self):
        self.assertEqual(clean_extracted_text("The plan was cancelled."),
                         "The plan was cancelled.")

    def test_attributed_quote_place_and_date_are_preserved(self):
        text = (
            'A company representative said, "We plan to open in Bacoor, '
            'Cavite on October 19, 2026."'
        )
        self.assertEqual(clean_extracted_text(text), text)

    def test_modal_negation_allegation_and_dates_are_kept(self):
        raw = (
            "# Preliminary Report\n"
            "The company did not confirm the planned June 2007 release.\n"
            "Witnesses alleged that the launch had occurred in May.\n"
        )
        clean = clean_extracted_text(raw)
        self.assertIn("did not confirm", clean)
        self.assertIn("planned June 2007", clean)
        self.assertIn("alleged", clean)

    def test_in_prose_citation_preserves_statement(self):
        raw = (
            "# Civic Update\n"
            "The agency [announced the planned closure](https://agency.example/notice) "
            "for Bacoor, Cavite on October 19, 2026.\n"
        )
        clean = clean_extracted_text(raw)
        self.assertIn("announced the planned closure", clean)
        self.assertNotIn("https://agency.example", clean)

    def test_no_proposition_or_empty_content_returns_empty(self):
        for raw in (None, "", "  ", "Home\nAccount\nShop and Learn\nPrivacy"):
            with self.subTest(raw=raw):
                self.assertEqual(clean_extracted_text(raw), "")

    def test_does_not_truncate_in_middle_of_sentence(self):
        sentence = (
            "The city announced that the planned closure would not proceed "
            "in Bacoor, Cavite on October 19, 2026."
        )
        raw = "# Civic Update\n" + "\n".join([sentence] * 110)
        clean = clean_extracted_text(raw)
        self.assertLessEqual(len(clean), 3000)
        self.assertEqual(clean.count(sentence), 29)
        self.assertTrue(clean.endswith(sentence))

    def test_parody_claim_text_is_not_rewritten(self):
        raw = "# Local Reports\nThe parody article claimed that rain had turned into candy."
        self.assertIn(
            "The parody article claimed that rain had turned into candy.",
            clean_extracted_text(raw),
        )
