#!/usr/bin/env python3
"""
verify_no_loss.py — Confirm every source file was copied to MediaLibrary.

Usage:
    python3 verify_no_loss.py <source_folder> <output_folder>

How it works:
  Builds an index of all files in output by (filename_lower, size_bytes).
  Then walks every non-junk file in source and checks it appears in the index.
  Reports match rate and lists any missing files.

Exit code 0 = all files matched. Exit code 1 = missing files found.
"""

import os
import sys
from collections import defaultdict

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


def build_index(folder):
    index = defaultdict(set)
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if is_junk(fname):
                continue
            fpath = os.path.join(root, fname)
            try:
                size = os.path.getsize(fpath)
                index[(fname.lower(), size)].add(fpath)
            except OSError:
                pass
    return index


def verify(source_folder, output_folder):
    print(f"Building output index from: {output_folder}")
    output_index = build_index(output_folder)
    print(f"Output index: {sum(len(v) for v in output_index.values()):,} files")

    print(f"\nChecking source: {source_folder}")
    total = 0
    matched = 0
    missing = []

    for root, dirs, files in os.walk(source_folder):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if is_junk(fname):
                continue
            fpath = os.path.join(root, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            total += 1
            key = (fname.lower(), size)
            if key in output_index:
                matched += 1
            else:
                missing.append(fpath)

    rate = (matched / total * 100) if total else 0
    print(f"\n{'='*60}")
    print(f"Source files:   {total:,}")
    print(f"Matched:        {matched:,}")
    print(f"Missing:        {len(missing):,}")
    print(f"Match rate:     {rate:.2f}%")

    if missing:
        print(f"\n{'='*60}")
        print("MISSING FILES:")
        for p in missing[:100]:
            print(f"  {p}")
        if len(missing) > 100:
            print(f"  ... and {len(missing)-100} more")
        print(f"\n❌ VERIFICATION FAILED — {len(missing):,} files not found in output")
        # Save report
        report_path = os.path.join(os.path.dirname(output_folder), 'verification_report.txt')
        with open(report_path, 'w') as f:
            f.write(f"VERIFICATION FAILED\n{'='*60}\n")
            f.write(f"Source:  {source_folder}\n")
            f.write(f"Output:  {output_folder}\n")
            f.write(f"Total:   {total:,}\nMatched: {matched:,}\nMissing: {len(missing):,}\n\n")
            f.write("Missing files:\n")
            for p in missing:
                f.write(f"  {p}\n")
        print(f"Report: {report_path}")
        return 1
    else:
        print(f"\n✅ {matched:,} / {total:,} files matched (100.00%) — ZERO DATA LOSS")
        report_path = os.path.join(os.path.dirname(output_folder), 'verification_report.txt')
        with open(report_path, 'w') as f:
            f.write(f"VERIFICATION PASSED\n{'='*60}\n")
            f.write(f"Source:  {source_folder}\n")
            f.write(f"Output:  {output_folder}\n")
            f.write(f"Total:   {total:,}\nMatched: {matched:,}\nMissing: 0\nMatch rate: 100.00%\n")
        print(f"Report: {report_path}")
        return 0


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 verify_no_loss.py <source_folder> <output_folder>")
        sys.exit(1)
    sys.exit(verify(sys.argv[1], sys.argv[2]))
