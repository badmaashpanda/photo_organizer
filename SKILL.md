---
name: organize-photos
description: >
  Helps users clean and organize a personal photo/video backup folder. Use this
  skill whenever someone wants to sort, deduplicate, or reorganize a large photo
  library, backup folder, or media archive. Trigger on phrases like "organize my
  photos", "clean up my photo backup", "sort photos by year", "find duplicate
  photos", "arrange my media folder", or any request involving cleaning up a
  folder full of images and videos — even if they don't use the word "skill".
  This skill guides the full pipeline: scan → deduplicate → organize by year →
  rename folders with context → verify zero data loss.
---

# Photo Organizer Skill

This skill walks through a complete pipeline to clean and organize a personal
photo/video backup. It generates Python scripts to do the heavy lifting so the
user can run them locally on large libraries (hundreds of GB) without timeouts.

## Ground Rules

- **Never modify the source folder.** Every operation is copy-only.
- **Leave ZIP files as-is** — copy them alongside their parent folder.
- **Skip system junk**: `.DS_Store`, `._*`, `Thumbs.db`, `.db`, `.ini`,
  `.lnk`, Spotlight indexes (`*.spotlight*`), etc.
- **macOS case-insensitive filesystem warning**: Never rename a folder to a
  name that differs only in case (e.g. `Siya_IPAD` → `Siya_iPad`). This will
  cause the folder to merge with itself and delete files. Always check before
  any rename.

---

## Pipeline Overview

```
Step 1 → Scan source         (document size, counts, types)
Step 2 → Dedup scan          (find all duplicate files, read-only)
Step 3 → Organize by year    (copy unique files; dupes → duplicates/)
Step 4 → Rename folders      (use visual inspection + folder name context)
Step 5 → Verify              (confirm 100% of source files present in output)
```

Do **not** skip steps or reorder them. Dedup must come before organizing, and
verification must come last.

---

## Step 1: Scan the Source Folder

Before writing any scripts, scan the source folder and present a table:

| Metric | Value |
|--------|-------|
| Total size (Finder/du) | … |
| Total files | … |
| Top-level subfolders | … |

Also show a **file count by extension** table (JPG, HEIC, PNG, MOV, MP4, AAE,
PDF, ZIP, system junk, etc.). This documents the source for the user's records.

Ask the user to confirm the source path and output path before proceeding.

---

## Step 2: Deduplication Script

Generate `/path/to/source/../dedup_scan.py` using the template in
`scripts/dedup_scan.py`. Key algorithm:

1. Walk source, skip junk files
2. Group files by byte size — files with a unique size cannot be duplicates
3. For size-collision groups: compute partial MD5 (first 8 KB)
4. For partial-hash collisions: compute full MD5
5. Output `dedup_report.json` (groups of identical files) and
   `dedup_summary.txt` (human-readable top duplicates by wasted space)

Tell the user to run the script and share the summary. Typical runtime: 15–40
minutes for 500 GB depending on drive speed.

---

## Step 3: Organize by Year Script

Generate `organize_photos.py` using the template in
`scripts/organize_photos.py`. Key behavior:

**Year determination priority** (use the first one that works):
1. EXIF `DateTimeOriginal` — most reliable for camera photos
2. Filename pattern — e.g. `20200419_`, `2024-02-18`, `IMG_20191205`
3. Folder name hint — e.g. a folder called `2018 LA` → year 2018
4. File `mtime` — last resort

**Output structure:**
```
MediaLibrary/
  2013/
    Siya_Sorted/
    India_Family/
    …
  2018/
    LA_Trip/
    …
  duplicates/        ← duplicate copies go here
  non_media/         ← PDFs, DOCX, PPTX, etc.
  Unknown_Year/      ← files where no year could be determined
```

**EXIF reading on macOS:** Use `pillow` + `pillow-heif` for HEIC support.
Install in a venv:
```bash
python3 -m venv /tmp/photo_venv
/tmp/photo_venv/bin/pip install pillow pillow-heif
```

Use `safe_copy(src, dst, skip_existing=True)` — if the destination already
exists, skip (don't append `_1`). This allows the script to be re-run after
a timeout without creating duplicates.

**Context folder names:** Use the source folder name (cleaned up) as the
subfolder name under the year. Strip redundant year suffixes when the year
folder already provides that context (e.g. `2018_LA_Trip` under `2018/`
becomes just `LA_Trip`).

Generate a `MediaLibrary_mapping.txt` log (one line per file:
`SOURCE → DESTINATION [action] (year_method)`) and `MediaLibrary_stats.txt`.

---

## Step 4: Rename Folders for Context

After the copy is done, offer to rename generic or vague folder names. To do
this well:

1. List all subfolder names across all year folders
2. Identify vague names: `PhotosVideos`, `WIP`, `MoreSnaps`, `DCIM`,
   `Unsorted`, `New folder`, `WIP`, backup source names like
   `Google_Photos_001`, `iPhone_Backup`, etc.
3. For each vague folder, sample 3–5 images from it using the Read tool to
   view the actual photos and understand the content
4. Propose a rename table with the reason for each rename
5. Wait for user approval before executing

**Rename safety rules:**
- Never rename if the new name differs only by case on macOS
- When merging two folders (e.g. `Home_Ghar` + `Home_Photos` → `Home_Photos`),
  move the *contents* of one into the other using `shutil.move`, then remove
  the empty source — never use `os.rename` for merges on case-insensitive
  filesystems

Generate `rename_folders.py` for approved renames rather than running `mv`
directly, so the user can review the script before running.

---

## Step 5: Verification Script

Generate `verify_no_loss.py` using the template in
`scripts/verify_no_loss.py`. It:

1. Builds an index of all files in `MediaLibrary/` by `(filename_lower, size)`
2. Walks every non-junk file in the source
3. Checks each one appears in the index
4. Reports match rate and lists any missing files

A passing run looks like:
```
✅ 83,449 / 83,449 files matched (100.00%) — ZERO DATA LOSS
```

If files are missing, the script lists them with their source paths so they can
be individually re-copied.

---

## Documentation to Generate

At the end of the pipeline, produce a summary markdown file with:
- Source folder stats (size, file count, types)
- Dedup results (groups found, excess copies, space saved)
- Year-by-year file counts in MediaLibrary
- Full source → destination folder mapping table
- List of all generated files (scripts, logs, reports)

---

## Handling Large Libraries (timeouts)

If the user's library is >100 GB, warn them that scripts will take 20–60+
minutes and should be run directly in the terminal, not inside Claude Code
(to avoid session timeouts). Provide ready-to-run terminal commands.

If a script was interrupted mid-run, the `skip_existing=True` behavior in
`safe_copy` means it's safe to re-run — it will pick up where it left off.

---

## Read the bundled scripts

- `scripts/dedup_scan.py` — complete dedup script template
- `scripts/organize_photos.py` — complete organizer script template  
- `scripts/verify_no_loss.py` — complete verifier script template

Adapt these templates to the user's specific source and output paths before
handing them off.
