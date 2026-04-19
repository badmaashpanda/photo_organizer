#!/usr/bin/env python3
"""
organize_photos.py — Copy and organize a photo/video library by year.

Usage:
    python3 organize_photos.py <source_folder> <output_folder> <dedup_report.json>

Requirements:
    pip install pillow pillow-heif

What it does:
  - Reads the dedup report to know which files are duplicates
  - For each file in source:
      - Duplicates  → <output>/duplicates/<context>/
      - Documents   → <output>/non_media/<type>/
      - Media       → <output>/<year>/<context>/
  - Determines year from: EXIF → filename → folder hint → mtime
  - safe_copy skips files that already exist (safe to re-run after timeout)
  - Generates MediaLibrary_mapping.txt and MediaLibrary_stats.txt
"""

import os
import sys
import json
import re
import shutil
import time
from collections import defaultdict

try:
    from PIL import Image
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("WARNING: pillow/pillow-heif not installed. EXIF dates unavailable.")
    print("Run: pip install pillow pillow-heif")

# ---------- Classification ----------

PHOTO_EXTS = {'.jpg', '.jpeg', '.heic', '.png', '.bmp', '.gif', '.psd',
              '.tiff', '.tif', '.webp', '.cr2', '.nef', '.arw', '.dng'}
VIDEO_EXTS = {'.mov', '.mp4', '.mpg', '.mpeg', '.avi', '.mts', '.m4v',
              '.3gp', '.wmv', '.flv', '.mkv', '.vob', '.m2ts'}
AUDIO_EXTS = {'.mp3', '.m4a', '.wav', '.aac', '.flac', '.ogg'}
SIDECAR_EXTS = {'.aae', '.thm', '.xmp'}
DOC_EXTS = {'.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls',
            '.txt', '.rtf', '.csv'}
ARCHIVE_EXTS = {'.zip', '.gz', '.tar', '.rar', '.7z'}

JUNK_NAMES = {'.ds_store', 'thumbs.db', 'desktop.ini', '.picasa.ini'}
JUNK_PREFIXES = ('._', '.spotlight')


def is_junk(name):
    nl = name.lower()
    if nl in JUNK_NAMES:
        return True
    if any(nl.startswith(p) for p in JUNK_PREFIXES):
        return True
    _, ext = os.path.splitext(nl)
    if ext in {'.db', '.lnk', '.ini'}:
        return True
    return False


def classify(path):
    _, ext = os.path.splitext(path.lower())
    if ext in PHOTO_EXTS:
        return 'photo'
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in AUDIO_EXTS:
        return 'audio'
    if ext in SIDECAR_EXTS:
        return 'sidecar'
    if ext in DOC_EXTS:
        return 'non_media'
    if ext in ARCHIVE_EXTS:
        return 'archive'
    return 'other'


# ---------- Year Detection ----------

YEAR_RE = re.compile(r'(?<!\d)(19[89]\d|20[0-2]\d)(?!\d)')


def year_from_exif(path):
    if not HAS_PILLOW:
        return None
    try:
        img = Image.open(path)
        exif = img.getexif()
        if exif:
            # Tag 36867 = DateTimeOriginal
            dt = exif.get(36867) or exif.get(306)
            if dt:
                m = YEAR_RE.search(str(dt))
                if m:
                    return int(m.group()), 'exif'
    except Exception:
        pass
    return None


def year_from_filename(name):
    m = YEAR_RE.search(name)
    if m:
        return int(m.group()), 'filename'
    return None


def year_from_folder(path, source_root):
    rel = os.path.relpath(path, source_root)
    parts = rel.split(os.sep)
    for part in parts:
        m = YEAR_RE.search(part)
        if m:
            return int(m.group()), 'folder_hint'
    return None


def year_from_mtime(path):
    try:
        t = os.path.getmtime(path)
        import datetime
        yr = datetime.datetime.fromtimestamp(t).year
        if 1990 <= yr <= 2030:
            return yr, 'mtime'
    except Exception:
        pass
    return None


def get_year(path, source_root):
    fname = os.path.basename(path)
    _, ext = os.path.splitext(fname.lower())
    if ext in PHOTO_EXTS | VIDEO_EXTS:
        result = year_from_exif(path)
        if result:
            return result
    result = year_from_filename(fname)
    if result:
        return result
    result = year_from_folder(path, source_root)
    if result:
        return result
    result = year_from_mtime(path)
    if result:
        return result
    return None, 'unknown'


# ---------- Context Folder Name ----------

def context_name(path, source_root):
    """Return a clean folder name from the source path context."""
    rel = os.path.relpath(path, source_root)
    parts = rel.split(os.sep)
    if len(parts) >= 2:
        folder = parts[0]
    else:
        folder = 'Misc'
    # Clean up the name
    name = folder.replace(' ', '_').replace('(', '').replace(')', '')
    # Strip redundant year prefixes/suffixes (year folder already handles that)
    name = re.sub(r'^(19[89]\d|20[0-2]\d)[_\-]?', '', name)
    name = re.sub(r'[_\-]?(19[89]\d|20[0-2]\d)$', '', name)
    return name or 'Misc'


# ---------- Safe Copy ----------

def safe_copy(src, dst, skip_existing=True):
    if os.path.exists(dst):
        if skip_existing:
            return None  # already copied in a previous run
        base, ext = os.path.splitext(dst)
        counter = 1
        while os.path.exists(dst):
            dst = f"{base}_{counter}{ext}"
            counter += 1
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst


# ---------- Main ----------

def organize(source_folder, output_folder, dedup_report_path):
    source_folder = source_folder.rstrip('/')
    os.makedirs(output_folder, exist_ok=True)

    # Load duplicate set (all files that are excess copies)
    dup_files = set()
    print(f"Loading dedup report: {dedup_report_path}")
    with open(dedup_report_path) as f:
        report = json.load(f)
    for group in report['groups']:
        # Keep the first file (best path), mark the rest as duplicates
        for fpath in group['files'][1:]:
            dup_files.add(os.path.normpath(fpath))
    print(f"Duplicate files to redirect: {len(dup_files):,}")

    # Stats
    stats = defaultdict(int)
    mapping_lines = []

    total = 0
    t0 = time.time()

    for root, dirs, files in os.walk(source_folder):
        dirs[:] = sorted([d for d in dirs if not d.startswith('.')])
        for fname in files:
            if is_junk(fname):
                stats['skipped_junk'] += 1
                continue

            src = os.path.join(root, fname)
            norm_src = os.path.normpath(src)
            category = classify(src)
            total += 1

            if total % 2000 == 0:
                elapsed = time.time() - t0
                print(f"  Processed {total:,} files ({elapsed/60:.1f} min)...", flush=True)

            # --- Duplicates ---
            if norm_src in dup_files:
                ctx = context_name(src, source_folder)
                dst = os.path.join(output_folder, 'duplicates', ctx, fname)
                result = safe_copy(src, dst)
                action = 'duplicate'
                stats['duplicate'] += 1

            # --- Non-media documents ---
            elif category == 'non_media':
                dst = os.path.join(output_folder, 'non_media', 'documents', fname)
                result = safe_copy(src, dst)
                action = 'non_media'
                stats['non_media'] += 1

            elif category == 'archive':
                ctx = context_name(src, source_folder)
                dst = os.path.join(output_folder, 'non_media', 'archives', ctx, fname)
                result = safe_copy(src, dst)
                action = 'archive'
                stats['archive'] += 1

            elif category == 'other':
                dst = os.path.join(output_folder, 'non_media', 'other', fname)
                result = safe_copy(src, dst)
                action = 'non_media_other'
                stats['non_media_other'] += 1

            # --- Media (photo / video / audio / sidecar) ---
            else:
                year, method = get_year(src, source_folder)
                year_str = str(year) if year else 'Unknown_Year'
                ctx = context_name(src, source_folder)
                dst = os.path.join(output_folder, year_str, ctx, fname)
                result = safe_copy(src, dst)
                action = category
                stats[category] += 1
                stats[f'year_{year_str}'] += 1

            rel_src = os.path.relpath(src, os.path.dirname(source_folder))
            rel_dst = os.path.relpath(dst, os.path.dirname(output_folder)) if result else '(skipped-existing)'
            mapping_lines.append(f"{rel_src}  ->  {rel_dst}  [{action}]")

    # Write mapping log
    mapping_path = os.path.join(os.path.dirname(output_folder), 'MediaLibrary_mapping.txt')
    with open(mapping_path, 'w') as f:
        f.write('\n'.join(mapping_lines))
    print(f"\nMapping log: {mapping_path} ({len(mapping_lines):,} entries)")

    # Write stats
    stats_path = os.path.join(os.path.dirname(output_folder), 'MediaLibrary_stats.txt')
    with open(stats_path, 'w') as f:
        f.write(f"MediaLibrary Organization Stats\n{'='*50}\n")
        f.write(f"Total files processed: {total:,}\n")
        f.write(f"Skipped (junk):        {stats['skipped_junk']:,}\n\n")
        f.write("By category:\n")
        for k, v in sorted(stats.items()):
            if not k.startswith('year_') and k != 'skipped_junk':
                f.write(f"  {k:<20} {v:>8,}\n")
        f.write("\nBy year:\n")
        for k, v in sorted((k, v) for k, v in stats.items() if k.startswith('year_')):
            f.write(f"  {k[5:]:<10} {v:>8,}\n")
    print(f"Stats: {stats_path}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f} minutes. {total:,} files processed.")


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python3 organize_photos.py <source> <output> <dedup_report.json>")
        sys.exit(1)
    organize(sys.argv[1], sys.argv[2], sys.argv[3])
