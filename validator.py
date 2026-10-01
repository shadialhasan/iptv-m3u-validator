# -*- coding: utf-8 -*-
"""
High-Speed Asynchronous IPTV M3U Playlist Validator & Filter
Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>
Phone: +963934005922
Copyright (c) 2026 MHD. Shadi AL-Hasan
"""

import os
import sys
import re
import time
import logging
import urllib.request
import urllib.error
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Configure logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format=LOG_FORMAT)
logger = logging.getLogger("M3UValidator")


class M3UValidator:
    """Concurrent validator and filter for IPTV M3U/M3U8 playlists."""

    def __init__(
        self,
        m3u_path: Path,
        max_workers: int = 15,
        timeout: int = 4,
        user_agent: str = "Mozilla/5.0 (VLC/3.0.18)",
    ):
        self.m3u_path = Path(m3u_path)
        self.max_workers = int(os.getenv("DEFAULT_MAX_WORKERS", max_workers))
        self.timeout = int(os.getenv("DEFAULT_TIMEOUT", timeout))
        self.user_agent = os.getenv("USER_AGENT", user_agent)
        self.alive_channels = []
        self.stats = {
            "total": 0,
            "alive": 0,
            "dead": 0,
            "elapsed_seconds": 0.0,
            "streams_per_second": 0.0,
        }

    def check_stream(self, channel: dict) -> dict:
        """Validate single stream endpoint with HTTP HEAD/GET request."""
        url = channel["url"]
        start_time = time.perf_counter()
        channel_copy = dict(channel)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
                method="HEAD",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status in (200, 206, 301, 302, 307, 308):
                        channel_copy["status"] = "ALIVE"
                        channel_copy["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
                        return channel_copy
            except (urllib.error.HTTPError, urllib.error.URLError):
                # Fallback to standard GET request if HEAD is rejected by media server
                get_req = urllib.request.Request(
                    url,
                    headers={"User-Agent": self.user_agent, "Range": "bytes=0-1024"},
                )
                with urllib.request.urlopen(get_req, timeout=self.timeout) as resp:
                    if resp.status in (200, 206):
                        channel_copy["status"] = "ALIVE"
                        channel_copy["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
                        return channel_copy
        except Exception as e:
            logger.debug("Stream check failed for %s: %s", url, e)

        channel_copy["status"] = "DEAD"
        channel_copy["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        return channel_copy

    def parse_m3u(self, content: str) -> list:
        """Parse raw M3U text content into structured channel objects."""
        raw_lines = content.splitlines()
        channels = []
        current_meta = ""
        current_title = ""

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF"):
                current_meta = line
                # Extract channel title if available
                title_match = re.search(r",([^,]+)$", line)
                current_title = title_match.group(1).strip() if title_match else "Unknown"
            elif line.startswith("http://") or line.startswith("https://") or line.startswith("rtmp://"):
                channels.append({
                    "meta": current_meta if current_meta else f'#EXTINF:-1,{current_title or "Stream"}',
                    "title": current_title or "Stream",
                    "url": line,
                })
                current_meta = ""
                current_title = ""

        return channels

    def parse_and_validate(self, output_file: Path = None) -> list:
        """Parse M3U file, execute concurrent validation, log performance, and optionally export clean file."""
        if not self.m3u_path.exists():
            raise FileNotFoundError(f"Playlist file not found: {self.m3u_path}")

        logger.info("[*] Reading M3U playlist: %s", self.m3u_path)
        content = self.m3u_path.read_text(encoding="utf-8", errors="ignore")
        channels = self.parse_m3u(content)
        self.stats["total"] = len(channels)

        logger.info(
            "[*] Extracted %d stream URLs. Testing connectivity with %d threads (timeout: %ds)...",
            len(channels),
            self.max_workers,
            self.timeout,
        )

        perf_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(self.check_stream, channels))
        elapsed = time.perf_counter() - perf_start

        alive = [r for r in results if r.get("status") == "ALIVE"]
        dead = [r for r in results if r.get("status") == "DEAD"]

        self.stats["alive"] = len(alive)
        self.stats["dead"] = len(dead)
        self.stats["elapsed_seconds"] = round(elapsed, 3)
        self.stats["streams_per_second"] = round(len(channels) / elapsed, 2) if elapsed > 0 else 0.0
        self.alive_channels = alive

        logger.info(
            "[+] Validation completed in %.2fs: %d/%d streams active (%.2f streams/sec).",
            self.stats["elapsed_seconds"],
            self.stats["alive"],
            self.stats["total"],
            self.stats["streams_per_second"],
        )

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for ch in alive:
                    f.write(f"{ch['meta']}\n{ch['url']}\n")
            logger.info("[+] Filtered clean playlist saved to: %s", output_path)

        return alive


def main():
    parser = argparse.ArgumentParser(description="Validate IPTV M3U streams concurrently.")
    parser.add_argument("--input", "-i", required=True, help="Input .m3u or .m3u8 file")
    parser.add_argument("--output", "-o", default="clean_playlist.m3u", help="Output filtered playlist")
    parser.add_argument("--threads", "-t", type=int, default=20, help="Concurrent workers")
    parser.add_argument("--timeout", type=int, default=4, help="HTTP connection timeout in seconds")
    args = parser.parse_args()

    validator = M3UValidator(Path(args.input), max_workers=args.threads, timeout=args.timeout)
    validator.parse_and_validate(Path(args.output))


if __name__ == "__main__":
    main()
