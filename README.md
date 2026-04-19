# organize-photos — Claude Skill

A Claude Code skill that guides you through cleaning and organizing a personal
photo/video backup library. It handles deduplication, year-based sorting,
intelligent folder renaming, and zero-data-loss verification.

## What it does

1. **Scans** the source folder — documents size, file counts by type
2. **Deduplicates** — finds all duplicate files using a fast two-pass MD5
   approach (groups by size first, then hashes only collisions)
3. **Organizes by year** — copies unique files into `MediaLibrary/<year>/`,
   reading EXIF data for accurate dates
4. **Renames folders** — visually inspects sample images from generic folders
   (`WIP`, `MoreSnaps`, `PhotosVideos`) and suggests meaningful names
5. **Verifies** — confirms 100% of source files are present in the output

**The source folder is never modified. Everything is copy-only.**

## Installation

Copy this folder into your Claude Code skills directory, or install the
`.skill` file if available.

## Usage

Just tell Claude:
- "organize my photos"
- "clean up my photo backup folder"
- "sort my photos by year and find duplicates"
- "I have a folder of 500 GB of photos, help me organize it"

Claude will guide you through each step and generate ready-to-run Python
scripts for the heavy lifting.

## Scripts

The `scripts/` folder contains three Python scripts that Claude will
customize for your paths:

| Script | Purpose |
|--------|---------|
| `dedup_scan.py` | Finds all duplicate files (read-only scan) |
| `organize_photos.py` | Copies files into year-based output structure |
| `verify_no_loss.py` | Confirms zero data loss after organization |

### Requirements

```bash
python3 -m venv /tmp/photo_venv
/tmp/photo_venv/bin/pip install pillow pillow-heif
```

### Running the scripts

```bash
# Step 1: Scan for duplicates
python3 dedup_scan.py /path/to/photos /path/to/output

# Step 2: Organize (after reviewing dedup_report.json)
python3 organize_photos.py /path/to/photos /path/to/MediaLibrary /path/to/dedup_report.json

# Step 3: Verify
python3 verify_no_loss.py /path/to/photos /path/to/MediaLibrary
```

Scripts are safe to re-run after interruption — they skip files already copied.

## Output structure

```
MediaLibrary/
  2013/
    India_Family/
    Siya_Sorted/
    ...
  2018/
    LA_Trip/
    Hawaii/
    ...
  2023/
    Harshi_US_Trip/
    ...
  duplicates/        ← duplicate copies (not deleted, just separated)
  non_media/         ← PDFs, DOCX, PPTX, archives
  Unknown_Year/      ← files where no year could be determined
```
