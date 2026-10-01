# -*- coding: utf-8 -*-
"""
Automated Test Suite for IPTV M3U Playlist Validator
Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import shutil
import sys
import os

# Ensure validator is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from validator import M3UValidator


class TestM3UValidator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sample_m3u = Path(self.test_dir) / "test.m3u"
        self.sample_content = (
            "#EXTM3U\n"
            '#EXTINF:-1 tvg-id="Ch1" group-title="News",News Channel 1\n'
            "http://example.com/stream1.m3u8\n"
            '#EXTINF:-1 tvg-id="Ch2" group-title="Sports",Sports HD\n'
            "https://example.com/stream2.m3u8\n"
            "#EXTINF:-1,Generic Stream\n"
            "http://example.com/stream3.m3u8\n"
        )
        self.sample_m3u.write_text(self.sample_content, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_parse_m3u_structure(self):
        """Test M3U content parsing correctly extracts channels and metadata."""
        validator = M3UValidator(self.sample_m3u)
        channels = validator.parse_m3u(self.sample_content)

        self.assertEqual(len(channels), 3)
        self.assertEqual(channels[0]["title"], "News Channel 1")
        self.assertEqual(channels[0]["url"], "http://example.com/stream1.m3u8")
        self.assertTrue("tvg-id=\"Ch1\"" in channels[0]["meta"])

        self.assertEqual(channels[1]["title"], "Sports HD")
        self.assertEqual(channels[1]["url"], "https://example.com/stream2.m3u8")

        self.assertEqual(channels[2]["title"], "Generic Stream")
        self.assertEqual(channels[2]["url"], "http://example.com/stream3.m3u8")

    def test_parse_m3u_empty_or_invalid(self):
        """Test parsing empty or malformed strings does not raise exceptions."""
        validator = M3UValidator(self.sample_m3u)
        channels = validator.parse_m3u("")
        self.assertEqual(channels, [])

        channels = validator.parse_m3u("#EXTM3U\n#COMMENT ONLY\n")
        self.assertEqual(channels, [])

    @patch("urllib.request.urlopen")
    def test_check_stream_alive(self, mock_urlopen):
        """Test that stream returning HTTP 200 is marked as ALIVE with latency recorded."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        validator = M3UValidator(self.sample_m3u, timeout=2)
        channel = {"title": "Test", "url": "http://live.example.com/test.m3u8", "meta": "#EXTINF:-1,Test"}
        result = validator.check_stream(channel)

        self.assertEqual(result["status"], "ALIVE")
        self.assertIn("latency_ms", result)
        self.assertGreaterEqual(result["latency_ms"], 0.0)

    @patch("urllib.request.urlopen")
    def test_check_stream_dead(self, mock_urlopen):
        """Test that stream throwing network exception is marked as DEAD."""
        mock_urlopen.side_effect = Exception("Connection timed out")

        validator = M3UValidator(self.sample_m3u, timeout=1)
        channel = {"title": "Dead Stream", "url": "http://dead.example.com/stream.m3u8", "meta": "#EXTINF:-1,Dead"}
        result = validator.check_stream(channel)

        self.assertEqual(result["status"], "DEAD")
        self.assertIn("latency_ms", result)

    @patch("urllib.request.urlopen")
    def test_parse_and_validate_workflow(self, mock_urlopen):
        """Test end-to-end validation flow and clean playlist file generation."""
        # Setup mock: stream 1 and 2 alive, stream 3 dead
        def mock_urlopen_logic(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            if "stream3" in url:
                raise Exception("Host unreachable")
            mock_resp.status = 200
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        mock_urlopen.side_effect = mock_urlopen_logic

        output_clean = Path(self.test_dir) / "clean_output.m3u"
        validator = M3UValidator(self.sample_m3u, max_workers=2, timeout=2)
        alive_channels = validator.parse_and_validate(output_clean)

        self.assertEqual(len(alive_channels), 2)
        self.assertEqual(validator.stats["total"], 3)
        self.assertEqual(validator.stats["alive"], 2)
        self.assertEqual(validator.stats["dead"], 1)
        self.assertGreater(validator.stats["elapsed_seconds"], 0)

        # Verify output clean file
        self.assertTrue(output_clean.exists())
        output_content = output_clean.read_text(encoding="utf-8")
        self.assertTrue(output_content.startswith("#EXTM3U\n"))
        self.assertIn("http://example.com/stream1.m3u8", output_content)
        self.assertIn("https://example.com/stream2.m3u8", output_content)
        self.assertNotIn("http://example.com/stream3.m3u8", output_content)

    def test_file_not_found(self):
        """Test that non-existent input playlist raises FileNotFoundError."""
        validator = M3UValidator(Path(self.test_dir) / "non_existent.m3u")
        with self.assertRaises(FileNotFoundError):
            validator.parse_and_validate()


if __name__ == "__main__":
    unittest.main()
