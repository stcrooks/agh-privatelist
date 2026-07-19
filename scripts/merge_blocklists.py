#!/usr/bin/env python3
"""
Merge HaGeZi Pro and IPFire Advertising blocklists into a single deduplicated list.
 
Outputs two files (paths configurable via CLI flags or env vars):
  - merged-adblock.txt : AdBlock-style, one domain per line as ||domain^
  - merged-plain.txt   : plain hostnames, one per line (Unbound/dnsmasq/Pi-hole friendly)
 
Before writing new output, any existing merged-adblock.txt / merged-plain.txt
are backed up alongside them as merged-adblock_YYYY_MM_DD_HHMM.txt /
merged-plain_YYYY_MM_DD_HHMM.txt. Backups older than --retention-days
(default 3) are deleted automatically on each run.
 
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
from datetime import datetime, timedelta
from pathlib import Path
 
ADBLOCK_LINE_RE = re.compile(r"^\|\|([^\^]+)\^")
COMMENT_PREFIXES = ("!", "#")
BACKUP_NAME_RE = re.compile(r"^(?P<base>merged-(?:adblock|plain))_(?P<ts>\d{4}_\d{2}_\d{2}_\d{4})(?:_\d+)?\.txt$")
 
 
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
 
 
def _build_header(comment: str, source_note: str, total: int) -> list[str]:
    """Build a header block using `comment` as the line-prefix char ('!' or '#')."""
    sep = f"{comment} " + "-" * 85
    return [
        f"{comment} Title: HaGeZi Pro & IP Fire Ads Merged",
        f"{comment} Deduplicated union of HaGeZi Pro (filter_48) and {source_note}",
        sep,
        f"{comment} IPFire Advertising Blocklist",
        f"{comment} License       : CC BY-SA 4.0",
        f"{comment} For more information or to contribute:",
        f"{comment}    https://dbl.ipfire.org/",
        f"{comment}    https://dbl.ipfire.org/lists/ads/domains.txt",
        sep,
        f"{comment} HaGeZi's Pro DNS Blocklist",
        f"{comment} Homepage: https://github.com/hagezi/dns-blocklists",
        f"{comment} License: https://github.com/hagezi/dns-blocklists/blob/main/LICENSE",
        f"{comment} Issues: https://github.com/hagezi/dns-blocklists/issues",
        f"{comment} Disclaimer: https://github.com/hagezi/dns-blocklists/blob/main/README.md#disclaimer",
        sep,
        f"{comment} Total domains: {total}",
        sep,
    ]


def _backup_existing(path: Path, timestamp: str) -> None:
    """If `path` already exists, rename it in place to a timestamped backup."""
    if not path.exists():
        return
    backup_path = path.with_name(f"{path.stem}_{timestamp}{path.suffix}")
    # Guard against a name collision if the script runs twice in the same minute
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.stem}_{timestamp}_{counter}{path.suffix}")
        counter += 1
    path.rename(backup_path)
    print(f"Backed up existing {path.name} -> {backup_path.name}")
 
 
def _cleanup_old_backups(outdir: Path, retention_days: int, now: datetime | None = None) -> None:
    """Delete backup files older than retention_days, based on the timestamp in their filename."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=retention_days)
    for f in outdir.glob("merged-*.txt"):
        m = BACKUP_NAME_RE.match(f.name)
        if not m:
            continue  # not a backup file (e.g. the current merged-adblock.txt)
        try:
            ts = datetime.strptime(m.group("ts"), "%Y_%m_%d_%H%M")
        except ValueError:
            continue
        if ts < cutoff:
            f.unlink()
            print(f"Deleted old backup: {f.name}")
 
 
def write_outputs(domains: set[str], outdir: Path, source_note: str,
                   backup: bool = True, retention_days: int = 3) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    sorted_domains = sorted(domains)
 
    adblock_path = outdir / "merged-adblock.txt"
    plain_path = outdir / "merged-plain.txt"
 
    if backup:
        timestamp = datetime.now().strftime("%Y_%m_%d_%H%M")
        _backup_existing(adblock_path, timestamp)
        _backup_existing(plain_path, timestamp)
        _cleanup_old_backups(outdir, retention_days)
 
    header_adblock = _build_header("!", source_note, len(sorted_domains))
    header_plain = _build_header("#", source_note, len(sorted_domains))
 
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
    ap.add_argument("--no-backup", action="store_true", help="Skip backing up existing output files")
    ap.add_argument("--retention-days", type=int, default=3, help="Delete backups older than this many days (default: 3)")
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
 
    write_outputs(merged, Path(args.outdir), "IPFire Advertising Blocklist",
                  backup=not args.no_backup, retention_days=args.retention_days)
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 
