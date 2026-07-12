#!/usr/bin/env python3
"""
Merge HaGeZi Pro and IPFire Advertising blocklists into a single deduplicated list.

Outputs two files (paths configurable via CLI flags or env vars):
  - merged-adblock.txt : AdBlock-style, one domain per line as ||domain^
  - merged-plain.txt   : plain hostnames, one per line (Unbound/dnsmasq/Pi-hole friendly)

Usage:
  python3 merge_blocklists.py \
      --hagezi-url https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt \
      --ipfire-url https://dbl.ipfire.org/lists/ads/domains.txt \
      --outdir ./dist
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ADBLOCK_LINE_RE = re.compile(r"^\|\|([^\^]+)\^")
COMMENT_PREFIXES = ("!", "#")


def fetch(url_or_path: str) -> list[str]:
    """Fetch text content from a URL or local file path, return list of lines."""
    if url_or_path.startswith(("http://", "https://")):
        req = urllib.request.Request(url_or_path, headers={"User-Agent": "blocklist-merger/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    else:
        text = Path(url_or_path).read_text(encoding="utf-8", errors="replace")
    return text.splitlines()


def parse_adblock_style(lines: list[str]) -> set[str]:
    """Extract bare domains from AdBlock-style (||domain^) lines like HaGeZi's."""
    domains = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith(COMMENT_PREFIXES):
            continue
        m = ADBLOCK_LINE_RE.match(line)
        if m:
            domains.add(m.group(1).lower())
    return domains


def parse_plain_style(lines: list[str]) -> set[str]:
    """Extract bare domains from plain hostname-per-line lists like IPFire's."""
    domains = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        # Guard against accidental hosts-file format (0.0.0.0 example.com)
        parts = line.split()
        domain = parts[-1] if parts else ""
        if domain:
            domains.add(domain.lower())
    return domains


def write_outputs(domains: set[str], outdir: Path, source_note: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    sorted_domains = sorted(domains)

    adblock_path = outdir / "merged-adblock.txt"
    plain_path = outdir / "merged-plain.txt"

    header_adblock = [
        "! Merged HaGeZi Pro + IPFire Advertising Blocklist",
        f"! Deduplicated union of HaGeZi Pro (filter_48) and {source_note}",
        "! -----------------------------------------------------------------------------------",
        "! IPFire Advertising Blocklist",
        "! License       : CC BY-SA 4.0",
        "! For more information or to contribute:",
        "!    https://dbl.ipfire.org/",
        "!    https://dbl.ipfire.org/lists/ads/domains.txt",
        "! -----------------------------------------------------------------------------------",
        "! HaGeZi's Pro DNS Blocklist",
        "! Homepage: https://github.com/hagezi/dns-blocklists",
        "! License: https://github.com/hagezi/dns-blocklists/blob/main/LICENSE",
        "! Issues: https://github.com/hagezi/dns-blocklists/issues",
        "! Disclaimer: https://github.com/hagezi/dns-blocklists/blob/main/README.md#disclaimer",
        "! -----------------------------------------------------------------------------------",      
        f"! Total domains: {len(sorted_domains)}",
        "! -----------------------------------------------------------------------------------",
    ]
    header_plain = [
        "# Merged HaGeZi Pro + IPFire Advertising Blocklist",
        f"# Deduplicated union of HaGeZi Pro (filter_48) and {source_note}",
        "# -----------------------------------------------------------------------------------",
        "# IPFire Advertising Blocklist",
        "# License       : CC BY-SA 4.0",
        "# For more information or to contribute:",
        "#    https://dbl.ipfire.org/",
        "#    https://dbl.ipfire.org/lists/ads/domains.txt",
        "# -----------------------------------------------------------------------------------",
        "# HaGeZi's Pro DNS Blocklist",
        "# Homepage: https://github.com/hagezi/dns-blocklists",
        "# License: https://github.com/hagezi/dns-blocklists/blob/main/LICENSE",
        "# Issues: https://github.com/hagezi/dns-blocklists/issues",
        "# Disclaimer: https://github.com/hagezi/dns-blocklists/blob/main/README.md#disclaimer",
        "# -----------------------------------------------------------------------------------",      
        f"# Total domains: {len(sorted_domains)}",
        "# -----------------------------------------------------------------------------------",


      
    ]

    adblock_path.write_text(
        "\n".join(header_adblock + [f"||{d}^" for d in sorted_domains]) + "\n",
        encoding="utf-8",
    )
    plain_path.write_text(
        "\n".join(header_plain + sorted_domains) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(sorted_domains)} unique domains to:")
    print(f"  {adblock_path}")
    print(f"  {plain_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hagezi-url", required=True, help="URL or path to HaGeZi Pro list (AdBlock-style)")
    ap.add_argument("--ipfire-url", required=True, help="URL or path to IPFire Advertising list (plain)")
    ap.add_argument("--outdir", default="dist", help="Output directory (default: dist)")
    args = ap.parse_args()

    print(f"Fetching HaGeZi list from {args.hagezi_url} ...")
    hagezi_domains = parse_adblock_style(fetch(args.hagezi_url))
    print(f"  -> {len(hagezi_domains)} domains")

    print(f"Fetching IPFire list from {args.ipfire_url} ...")
    ipfire_domains = parse_plain_style(fetch(args.ipfire_url))
    print(f"  -> {len(ipfire_domains)} domains")

    merged = hagezi_domains | ipfire_domains
    print(f"Merged unique domains: {len(merged)} "
          f"(overlap: {len(hagezi_domains & ipfire_domains)})")

    write_outputs(merged, Path(args.outdir), "IPFire Advertising Blocklist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
  
