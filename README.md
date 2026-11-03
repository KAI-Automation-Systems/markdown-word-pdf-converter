# Markdown → DOCX / PDF Converter

Convert one or many `.md` files into **Word (.docx)** or **PDF** so other
people can read them without a Markdown viewer.

It is pure Python (no Pandoc, LaTeX, or other external programs) and works on
Windows ARM64.

## Quick start (easiest)

Double-click **`Convert (GUI).bat`**. A window opens where you:

1. Click **Add files…** and select all the `.md` files you want (you can
   multi-select with Ctrl / Shift).
2. Pick **Word (.docx)** or **PDF (.pdf)**.
3. Choose the folder to save into (leave empty to save next to each source
   file).
4. Click **Convert**.

## Command line (batch)

Open a terminal in this folder and run, for example:

```powershell
# Convert specific files to Word
py -3.12 md_converter.py notes1.md notes2.md --format docx --outdir output

# Convert every .md in a folder to PDF
py -3.12 md_converter.py "C:\path\to\folder" --format pdf --outdir output

# Convert with a wildcard, saving next to each source file
py -3.12 md_converter.py *.md --format docx
```

Options:

- `--format {docx,pdf}` — output format (default: `docx`).
- `--outdir FOLDER` — where to save (default: next to each source file).
- `--gui` — force the graphical window.

## Setup (only needed once, if not already installed)

```powershell
py -3.12 -m pip install -r requirements.txt
```

## What is supported

Headings, bold/italic, ordered & unordered lists (nested), links, tables,
blockquotes, fenced code blocks, and Unicode/accented characters (e.g. Dutch:
café, naïef, déjà vu).

## Notes

- **DOCX** is produced via `python-docx` + `htmldocx`.
- **PDF** is produced via `fpdf2`, using the system Arial/Consolas fonts so
  accented characters render correctly.
- Each file is converted independently; if one fails the others still run, and
  the status log shows exactly what succeeded or failed.
