from __future__ import annotations

import unittest

from automation.validate_rendered_video import evaluate_video_metadata


def metadata(*, width=1080, height=1920, video_duration=63.0, include_audio=True):
    streams = [{"codec_type": "video", "width": width, "height": height}]
    if include_audio:
        streams.append({"codec_type": "audio"})
    return {"streams": streams, "format": {"duration": str(video_duration)}}


class RenderedVideoQualityTests(unittest.TestCase):
    def setUp(self):
        self.audio = {"format": {"duration": "60.0"}}

    def test_accepts_portrait_video_with_audio_and_expected_duration(self):
        report = evaluate_video_metadata(
            metadata(), self.audio,
            expected_aspect="9:16",
            min_duration=59.7,
            max_duration=68.0,
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["checks"]["aspect_ratio"], "passed")
        self.assertEqual(report["duration_delta_seconds"], 3.0)

    def test_rejects_missing_audio_stream(self):
        with self.assertRaisesRegex(ValueError, "no audio stream"):
            evaluate_video_metadata(
                metadata(include_audio=False), self.audio,
                expected_aspect="9:16",
                min_duration=59.7,
                max_duration=68.0,
            )

    def test_rejects_wrong_aspect_ratio(self):
        with self.assertRaisesRegex(ValueError, "aspect mismatch"):
            evaluate_video_metadata(
                metadata(width=1920, height=1080), self.audio,
                expected_aspect="9:16",
                min_duration=59.7,
                max_duration=68.0,
            )

    def test_rejects_video_shorter_than_narration(self):
        with self.assertRaisesRegex(ValueError, "shorter than narration"):
            evaluate_video_metadata(
                metadata(video_duration=58.0), self.audio,
                expected_aspect="9:16",
                min_duration=59.7,
                max_duration=68.0,
            )

    def test_rejects_video_exceeding_allowed_tail(self):
        with self.assertRaisesRegex(ValueError, "exceeds narration duration"):
            evaluate_video_metadata(
                metadata(video_duration=70.0), self.audio,
                expected_aspect="9:16",
                min_duration=59.7,
                max_duration=68.0,
            )

    def test_rejects_file_without_video_stream(self):
        with self.assertRaisesRegex(ValueError, "no video stream"):
            evaluate_video_metadata(
                {"streams": [{"codec_type": "audio"}], "format": {"duration": "60"}},
                self.audio,
                expected_aspect="9:16",
                min_duration=59.7,
                max_duration=68.0,
            )


if __name__ == "__main__":
    unittest.main()
