"""
Obsidian-to-JSON migration script.

Reads all .md files from the Halosight Knowledge Wiki vault, cleans Obsidian-specific
syntax, and outputs structured JSON ready for Supabase ingestion.

Usage:
    python migrate_obsidian.py
    python migrate_obsidian.py --vault "/path/to/vault" --out "./migration_output"
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_VAULT = Path.home() / "Desktop" / "Halosight Knowledge Wiki"
DEFAULT_OUT = Path(__file__).parent / "migration_output"

# Folders to skip entirely (templates, meta-folders with no content docs)
SKIP_FOLDERS = {"Templates"}

# Warn when a document's word count is below this threshold
MIN_WORD_COUNT = 10


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------

def extract_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (meta_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")

    meta: dict = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    # Parse tags list if present (tags: [a, b, c] or multi-line)
    raw_tags = meta.get("tags", "")
    if raw_tags.startswith("[") and raw_tags.endswith("]"):
        meta["tags"] = [t.strip().strip('"').strip("'") for t in raw_tags[1:-1].split(",") if t.strip()]
    elif raw_tags:
        meta["tags"] = [raw_tags]
    else:
        meta["tags"] = []

    return meta, body


def resolve_wikilinks(text: str) -> str:
    """Replace Obsidian wikilinks with plain text."""
    # Remove embedded files: ![[filename.ext]]
    text = re.sub(r"!\[\[([^\]]+)\]\]", "", text)

    # [[Note|Display Text]] → Display Text
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)

    # [[Note#Section]] → Note
    text = re.sub(r"\[\[([^\]#]+)#[^\]]*\]\]", r"\1", text)

    # [[Note]] → Note
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

    return text


def clean_obsidian_syntax(text: str) -> str:
    """Remove or normalize Obsidian-specific formatting."""
    # Dataview blocks
    text = re.sub(r"```dataview.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Obsidian callout markers — keep body, drop the [!TYPE] marker line
    # Pattern: > [!NOTE] or > [!WARNING] etc.
    text = re.sub(r"^> \[![A-Z]+\]\s*\n?", "", text, flags=re.MULTILINE)

    # HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip trailing whitespace from lines
    text = "\n".join(line.rstrip() for line in text.splitlines())

    return text.strip()


def extract_inline_tags(text: str) -> list[str]:
    """Pull #hashtag tokens from body text, excluding markdown headings."""
    tags = []
    for line in text.splitlines():
        if line.startswith("#"):
            continue  # skip heading lines
        tags.extend(re.findall(r"(?<!\[)#([A-Za-z][A-Za-z0-9_-]*)", line))
    return tags


def resolve_title(meta: dict, body: str, filepath: Path) -> str:
    """Derive title from frontmatter, first H1, or filename — in that order."""
    if meta.get("title"):
        return meta["title"].strip()

    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()

    return filepath.stem.replace("-", " ").replace("_", " ")


def count_words(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(md_file: Path, vault_root: Path) -> tuple[Optional[dict], list[str]]:
    """
    Process a single .md file.

    Returns (document_dict, warnings). document_dict is None if the file
    should be skipped entirely.
    """
    warnings: list[str] = []
    rel = md_file.relative_to(vault_root)
    parts = rel.parts  # e.g. ("01-Company Context", "Halosight Executive Overview.md")

    folder = parts[0] if len(parts) > 1 else "root"

    raw = md_file.read_text(encoding="utf-8", errors="replace")

    meta, body = extract_frontmatter(raw)
    body = resolve_wikilinks(body)
    body = clean_obsidian_syntax(body)

    title = resolve_title(meta, body, md_file)

    # Tags: frontmatter + inline hashtags, deduplicated, lowercased
    fm_tags = [t.lower() for t in meta.get("tags", [])]
    inline_tags = [t.lower() for t in extract_inline_tags(body)]
    tags = sorted(set(fm_tags + inline_tags))

    word_count = count_words(body)

    # Validation warnings
    if not body:
        warnings.append("empty content after cleanup")
    if word_count < MIN_WORD_COUNT:
        warnings.append(f"low word count ({word_count})")
    remaining_links = re.findall(r"\[\[", body)
    if remaining_links:
        warnings.append(f"unresolved wikilinks ({len(remaining_links)} found)")

    doc = {
        "title": title,
        "folder": folder,
        "category": folder,  # flat structure: category mirrors folder
        "content": body,
        "word_count": word_count,
        "tags": tags,
        "source_file": str(rel),
    }

    return doc, warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Obsidian vault to JSON")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT, help="Path to Obsidian vault")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    args = parser.parse_args()

    vault: Path = args.vault
    out_dir: Path = args.out

    if not vault.exists():
        print(f"ERROR: vault not found at {vault}", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(
        f for f in vault.rglob("*.md")
        if f.relative_to(vault).parts[0] not in SKIP_FOLDERS
    )

    documents: list[dict] = []
    report_entries: list[dict] = []
    skipped = 0

    for md_file in md_files:
        doc, warnings = process_file(md_file, vault)
        rel_str = str(md_file.relative_to(vault))

        if not doc["content"]:
            skipped += 1
            report_entries.append({"file": rel_str, "status": "skipped", "reason": "empty content"})
            continue

        documents.append(doc)
        status = "warning" if warnings else "ok"
        report_entries.append({"file": rel_str, "status": status, "warnings": warnings})

    # Write outputs
    output_file = out_dir / "migration_output.json"
    report_file = out_dir / "migration_report.json"

    output_file.write_text(json.dumps(documents, indent=2, ensure_ascii=False), encoding="utf-8")

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "vault": str(vault),
        "total_files_found": len(md_files),
        "documents_exported": len(documents),
        "skipped": skipped,
        "files_with_warnings": sum(1 for e in report_entries if e.get("status") == "warning"),
        "entries": report_entries,
    }
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Console summary
    print(f"\nMigration complete")
    print(f"  Vault:              {vault}")
    print(f"  Files found:        {len(md_files)}")
    print(f"  Documents exported: {len(documents)}")
    print(f"  Skipped:            {skipped}")
    print(f"  With warnings:      {report['files_with_warnings']}")
    print(f"\n  Output:  {output_file}")
    print(f"  Report:  {report_file}\n")

    # Print any warnings so they're visible in the terminal
    for entry in report_entries:
        if entry.get("warnings"):
            print(f"  WARN [{entry['file']}]: {', '.join(entry['warnings'])}")


if __name__ == "__main__":
    main()
