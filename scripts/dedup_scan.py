#!/usr/bin/env python3
"""
dedup_scan.py — Two-pass duplicate file detector.

Usage:
    python3 dedup_scan.py <source_folder> <output_dir>

Outputs:
    <output_dir>/dedup_report.json    — full duplicate groups (JSON)
    <output_dir>/dedup_summary.txt    — human-readable top duplicates

Algorithm:
    Pass 1: Group files by byte size. Unique sizes = definitely not dupes.
    Pass 2: For size-collision groups, compute partial MD5 (first 8 KB).
    Pass 3: For partial-hash collisions, compute full MD5.
This approach avoids hashing most files, making it fast on large libraries.
"""

import os
import sys
import json
import hashlib
import time
from collections import defaultdict

# Files to skip entirely
JUNK_NAMES = {'.ds_store', 'thumbs.db', 'desktop.ini', '.picasa.ini'}
JUNK_EXTS = {'.db', '.ini', '.lnk', '.bup', ''}
JUNK_PREFIXES = ('._', '.spotlight')


def is_junk(path):
    name = os.path.basename(path).lower()
    if name in JUNK_NAMES:
        return True
    if any(name.startswith(p) for p in JUNK_PREFIXES):
        return True
    _, ext = os.path.splitext(name)
    if ext in {'.db', '.lnk'}:
        return True
    return False


def partial_md5(path, chunk=8192):
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            h.update(f.read(chunk))
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def full_md5(path):
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def scan(source_folder, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Scanning {source_folder} ...")

    # --- Pass 1: group by size ---
    size_groups = defaultdict(list)
    total = 0
    skipped = 0
    for root, dirs, files in os.walk(source_folder):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if is_junk(fname):
                skipped += 1
                continue
            fpath = os.path.join(root, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                skipped += 1
                continue
            size_groups[size].append(fpath)
            total += 1
            if total % 5000 == 0:
                print(f"  Indexed {total} files...", flush=True)

    print(f"Total files: {total}, skipped junk: {skipped}")
    collision_files = sum(len(v) for v in size_groups.values() if len(v) > 1)
    unique_by_size = total - collision_files
    print(f"Unique by size (not dupes): {unique_by_size}")
    print(f"Files needing hash check: {collision_files}")

    # --- Pass 2: partial hash on size-collision groups ---
    partial_groups = defaultdict(list)
    hashed = 0
    for size, paths in size_groups.items():
        if len(paths) < 2:
            continue
        for p in paths:
            ph = partial_md5(p)
            if ph:
                partial_groups[(size, ph)].append(p)
            hashed += 1
            if hashed % 1000 == 0:
                print(f"  Partial-hashed {hashed}/{collision_files}...", flush=True)

    # --- Pass 3: full hash on partial-hash collisions ---
    dup_groups = []
    full_hashed = 0
    full_collision_files = sum(len(v) for v in partial_groups.values() if len(v) > 1)
    print(f"Files needing full hash: {full_collision_files}")

    for (size, ph), paths in partial_groups.items():
        if len(paths) < 2:
            continue
        full_hash_map = defaultdict(list)
        for p in paths:
            fh = full_md5(p)
            if fh:
                full_hash_map[fh].append(p)
            full_hashed += 1
            if full_hashed % 500 == 0:
                print(f"  Full-hashed {full_hashed}/{full_collision_files}...", flush=True)
        for fh, group in full_hash_map.items():
            if len(group) > 1:
                dup_groups.append({
                    'hash': fh,
                    'size_bytes': size,
                    'count': len(group),
                    'wasted_bytes': size * (len(group) - 1),
                    'files': group
                })

    # Sort by wasted space descending
    dup_groups.sort(key=lambda x: x['wasted_bytes'], reverse=True)

    total_excess = sum(g['count'] - 1 for g in dup_groups)
    total_wasted = sum(g['wasted_bytes'] for g in dup_groups)

    report = {
        'scanned': total,
        'skipped_junk': skipped,
        'unique_by_size': unique_by_size,
        'duplicate_groups': len(dup_groups),
        'total_excess_copies': total_excess,
        'wasted_bytes': total_wasted,
        'groups': dup_groups
    }

    report_path = os.path.join(output_dir, 'dedup_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved: {report_path}")

    # Human-readable summary
    summary_path = os.path.join(output_dir, 'dedup_summary.txt')
    with open(summary_path, 'w') as f:
        f.write(f"Dedup Scan Summary\n{'='*60}\n")
        f.write(f"Files scanned:        {total:,}\n")
        f.write(f"Skipped (junk):       {skipped:,}\n")
        f.write(f"Duplicate groups:     {len(dup_groups):,}\n")
        f.write(f"Excess copies:        {total_excess:,}\n")
        f.write(f"Wasted space:         {total_wasted / 1e9:.2f} GB\n\n")
        f.write(f"Top 50 largest duplicate groups:\n{'-'*60}\n")
        for i, g in enumerate(dup_groups[:50], 1):
            wasted_mb = g['wasted_bytes'] / 1e6
            f.write(f"\n#{i} — {g['count']} copies, {wasted_mb:.0f} MB wasted\n")
            for fp in g['files']:
                f.write(f"    {fp}\n")

    print(f"Summary saved: {summary_path}")
    print(f"\n{'='*60}")
    print(f"DUPLICATE GROUPS:  {len(dup_groups):,}")
    print(f"EXCESS COPIES:     {total_excess:,}")
    print(f"WASTED SPACE:      {total_wasted / 1e9:.2f} GB")
    print(f"{'='*60}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 dedup_scan.py <source_folder> <output_dir>")
        sys.exit(1)
    source = sys.argv[1].rstrip('/')
    output = sys.argv[2]
    t0 = time.time()
    scan(source, output)
    print(f"\nDone in {(time.time()-t0)/60:.1f} minutes.")
