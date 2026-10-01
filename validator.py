# -*- coding: utf-8 -*-
"""
High-Speed Asynchronous IPTV M3U Playlist Validator & Filter
Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>
Phone: +963934005922
Copyright (c) 2026 MHD. Shadi AL-Hasan
"""

import sys
import re
import urllib.request
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

class M3UValidator:
    def __init__(self, m3u_path: Path, max_workers: int = 15, timeout: int = 4):
        self.m3u_path = m3u_path
        self.max_workers = max_workers
        self.timeout = timeout
        self.alive_channels = []

    def check_stream(self, channel: dict) -> dict:
        url = channel["url"]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VLC/3.0.18)"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status in (200, 206):
                    channel["status"] = "ALIVE"
                    return channel
        except Exception:
            pass
        channel["status"] = "DEAD"
        return channel

    def parse_and_validate(self, output_file: Path):
        print(f"[*] Reading M3U playlist: {self.m3u_path}")
        raw_lines = self.m3u_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        channels = []
        current_meta = ""
        for line in raw_lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                current_meta = line
            elif line.startswith("http"):
                channels.append({"meta": current_meta, "url": line})
                current_meta = ""

        print(f"[*] Extracted {len(channels)} stream URLs. Testing connectivity with {self.max_workers} threads...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(self.check_stream, channels))

        alive = [r for r in results if r["status"] == "ALIVE"]
        print(f"\n[+] Validation complete: {len(alive)}/{len(channels)} streams active.")

        # Export clean playlist
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for ch in alive:
                f.write(f"{ch['meta']}\n{ch['url']}\n")

        print(f"[+] Filtered clean playlist saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Validate IPTV M3U streams concurrently.")
    parser.add_argument("--input", "-i", required=True, help="Input .m3u or .m3u8 file")
    parser.add_argument("--output", "-o", default="clean_playlist.m3u", help="Output filtered playlist")
    parser.add_argument("--threads", "-t", type=int, default=20, help="Concurrent workers")
    args = parser.parse_args()

    validator = M3UValidator(Path(args.input), max_workers=args.threads)
    validator.parse_and_validate(Path(args.output))

if __name__ == "__main__":
    main()
