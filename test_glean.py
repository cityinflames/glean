import unittest

import bible
import glean

THORN = """(Transcribed by TurboScribe. Go Unlimited to remove this message.)

(0:02 - 0:28)
When the Lord finally told him in verse 9, he got it. And he said to me, my grace is sufficient for you.

(1:40 - 2:10)
Paul understood 2 Corinthians 12:9. My grace is sufficient for you, for my strength is made perfect in weakness.

(8:00 - 8:20)
Enter by the narrow gate. Matthew 7:13-14 is the fork he preached.
"""


class ParseTests(unittest.TestCase):
    def test_turboscribe_times(self):
        segments = glean.parse_transcript(THORN)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0]["start"], 2)
        self.assertEqual(segments[0]["end"], 28)
        self.assertNotIn("TurboScribe", segments[0]["text"])

    def test_srt(self):
        text = "1\n00:01:02,000 --> 00:01:08,500\nLook up when you are joyful.\n"
        segments = glean.parse_transcript(text)
        self.assertEqual(segments[0]["start"], 62)
        self.assertAlmostEqual(segments[0]["end"], 68.5)

    def test_scripture_does_not_invent_a_book(self):
        segments = glean.parse_transcript(THORN)
        cites = glean.find_scripture(segments)
        notes = [item["note"] for item in cites if item["note"]]
        self.assertTrue(any("without a book" in note for note in notes))
        refs = [item["ref"] for item in cites]
        self.assertIn("2 Corinthians 12:9", refs)
        self.assertIn("Matthew 7:13-14", refs)

    def test_clips_keep_times(self):
        result = glean.glean(glean.parse_transcript(THORN), "Thorn")
        self.assertTrue(result["clips"])
        self.assertTrue(all(clip["start"] is not None for clip in result["clips"]))
        markdown = glean.to_markdown(result)
        self.assertIn("2 Corinthians 12:9", markdown)
        self.assertIn("–", markdown)

    def test_srt_skips_cue_numbers(self):
        text = (
            "470\n00:19:26,870 --> 00:19:32,290\nThey're saved inner men and women living in\n"
            "471\n00:19:32,290 --> 00:19:34,690\nlost material bodies.\n"
        )
        segments = glean.parse_transcript(text)
        joined = " ".join(segment["text"] for segment in segments)
        self.assertNotRegex(joined, r"\b470\b")
        self.assertIn("lost material bodies", joined)

    def test_punches_keep_spoken_words_and_times(self):
        text = """
1
00:19:26,870 --> 00:19:32,290
They're saved inner men and women living in

2
00:19:32,290 --> 00:19:34,690
lost material bodies.

3
00:19:35,390 --> 00:19:44,010
God's saving grace this side of the morning of the resurrection does not touch a single cell of the physical body.

4
00:19:44,950 --> 00:19:52,470
Not one cell in the brain, not one cell anywhere, including the rim of your toenail.

5
01:15:38,000 --> 01:15:52,000
Do not mess with God. If you don't remember a dead blame thing else I've said today, don't mess with God.
"""
        punches = glean.find_punches(glean.parse_transcript(text))
        self.assertGreaterEqual(len(punches), 2)
        joined = " ".join(item["text"].lower() for item in punches)
        self.assertIn("toenail", joined)
        self.assertIn("do not mess with god", joined)
        for punch in punches:
            self.assertIn(punch["hook"].split()[0].lower(), punch["text"].lower())
            self.assertIsNotNone(punch["start"])
            self.assertLessEqual(punch["end"] - punch["start"], 40)


class BibleTests(unittest.TestCase):
    def test_kjv_text_when_present(self):
        if not bible.available():
            self.skipTest("KJV file not downloaded")
        ref, text = bible.passage("Matthew", 7, 13, 14)
        self.assertEqual(ref, "Matthew 7:13-14")
        self.assertIn("strait", text.lower())


if __name__ == "__main__":
    unittest.main()
