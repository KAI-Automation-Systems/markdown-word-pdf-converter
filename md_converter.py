#!/usr/bin/env python3
"""
Markdown -> DOCX / PDF batch converter.

Two ways to use it:

1. GUI (default):  just run the program with no arguments
       py -3.12 md_converter.py
   Pick one or more .md files, choose DOCX or PDF, choose an output
   folder, and click Convert.

2. Command line (batch):
       py -3.12 md_converter.py notes1.md notes2.md --format docx --outdir out
       py -3.12 md_converter.py *.md --format pdf

Pure Python, no external binaries required (works on Windows ARM64).
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

import markdown as md_lib

# Markdown features we enable. "extra" already bundles tables, fenced code,
# footnotes, definition lists, etc. "sane_lists" makes nested lists behave.
MD_EXTENSIONS = ["extra", "sane_lists", "toc"]

# Candidate Windows fonts (regular, bold, italic, bold-italic).
_FONT_CANDIDATES = {
    "Body": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Mono": ("consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
}


# --------------------------------------------------------------------------- #
# Markdown -> HTML
# --------------------------------------------------------------------------- #
def read_markdown(md_path: Path) -> str:
    return md_path.read_text(encoding="utf-8", errors="replace")


def md_to_html_fragment(md_text: str) -> str:
    """Convert markdown text to an HTML fragment (no <html> wrapper)."""
    return md_lib.markdown(md_text, extensions=MD_EXTENSIONS, output_format="html")


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def convert_to_docx(md_path: Path, out_path: Path) -> None:
    from docx import Document
    from htmldocx import HtmlToDocx

    html = md_to_html_fragment(read_markdown(md_path))
    document = Document()
    parser = HtmlToDocx()
    parser.add_html_to_document(html, document)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out_path))


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _register_unicode_fonts(pdf) -> tuple[str, str]:
    """Register Unicode-capable fonts so accented characters render.

    Returns (body_family, mono_family). Falls back to the built-in
    'helvetica'/'courier' if no TrueType fonts are found.
    """
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    styles = ["", "B", "I", "BI"]

    def try_family(name: str, files: tuple[str, ...]) -> bool:
        paths = [fonts_dir / f for f in files]
        if not all(p.exists() for p in paths):
            return False
        for style, path in zip(styles, paths):
            pdf.add_font(name, style, str(path))
        return True

    body = "Body" if try_family("Body", _FONT_CANDIDATES["Body"]) else "helvetica"
    mono = "Mono" if try_family("Mono", _FONT_CANDIDATES["Mono"]) else "courier"
    return body, mono


def convert_to_pdf(md_path: Path, out_path: Path) -> None:
    import logging

    from fpdf import FPDF
    from fpdf.fonts import TextStyle

    # fontTools logs noisy (harmless) warnings when subsetting some system
    # fonts, e.g. "MERG NOT subset". Keep our output clean.
    logging.getLogger("fontTools").setLevel(logging.ERROR)

    html = md_to_html_fragment(read_markdown(md_path))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=15, top=15, right=15)
    body_font, mono_font = _register_unicode_fonts(pdf)
    pdf.add_page()
    pdf.set_font(body_font, size=11)

    # Use the monospace family for <code>/<pre> blocks (modern tag_styles API).
    code_style = TextStyle(font_family=mono_font)
    pdf.write_html(
        html,
        font_family=body_font,
        tag_styles={"code": code_style, "pre": code_style},
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
CONVERTERS = {"docx": convert_to_docx, "pdf": convert_to_pdf}


def convert_one(md_path: Path, fmt: str, outdir: Path | None) -> Path:
    """Convert a single markdown file. Returns the output path."""
    md_path = Path(md_path)
    target_dir = Path(outdir) if outdir else md_path.parent
    out_path = target_dir / f"{md_path.stem}.{fmt}"
    CONVERTERS[fmt](md_path, out_path)
    return out_path


def convert_many(files, fmt: str, outdir: Path | None, progress=None):
    """Convert many files. `progress(index, total, name, ok, message)` callback.

    Returns (successes, failures) lists of (path, message).
    """
    files = [Path(f) for f in files]
    total = len(files)
    successes, failures = [], []
    for i, md_path in enumerate(files, start=1):
        try:
            out_path = convert_one(md_path, fmt, outdir)
            successes.append((out_path, ""))
            if progress:
                progress(i, total, md_path.name, True, str(out_path))
        except Exception as exc:  # noqa: BLE001 - report per-file, keep going
            msg = f"{type(exc).__name__}: {exc}"
            failures.append((md_path, msg))
            if progress:
                progress(i, total, md_path.name, False, msg)
    return successes, failures


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run_cli(args) -> int:
    files = []
    for pattern in args.files:
        p = Path(pattern)
        if any(ch in pattern for ch in "*?[]"):
            files.extend(sorted(Path().glob(pattern)))
        elif p.is_dir():
            files.extend(sorted(p.glob("*.md")))
        else:
            files.append(p)

    files = [f for f in files if f.suffix.lower() in (".md", ".markdown")]
    if not files:
        print("No .md files matched.", file=sys.stderr)
        return 2

    outdir = Path(args.outdir) if args.outdir else None
    print(f"Converting {len(files)} file(s) to {args.format.upper()}"
          + (f" -> {outdir}" if outdir else " (next to each source file)"))

    def progress(i, total, name, ok, message):
        status = "OK " if ok else "FAIL"
        print(f"  [{i}/{total}] {status} {name}"
              + (f" -> {message}" if ok else f"  ({message})"))

    successes, failures = convert_many(files, args.format, outdir, progress)
    print(f"\nDone. {len(successes)} succeeded, {len(failures)} failed.")
    return 0 if not failures else 1


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    import customtkinter as ctk

    # --- Theme -------------------------------------------------------------- #
    ctk.set_appearance_mode("system")        # follow the OS light/dark setting
    ctk.set_default_color_theme("blue")

    ACCENT = "#2563eb"
    ACCENT_HOVER = "#1d4ed8"
    DANGER = "#ef4444"
    MUTED = ("#6b7280", "#9ca3af")           # (light, dark)
    CARD = ("#ffffff", "#1c1c20")
    SURFACE = ("#f4f5f7", "#161618")
    BORDER = ("#e5e7eb", "#2a2a2e")

    root = ctk.CTk()
    root.title("Markdown Converter")
    root.geometry("780x720")
    root.minsize(680, 640)
    root.configure(fg_color=SURFACE)

    font_title = ctk.CTkFont(family="Segoe UI Semibold", size=22, weight="bold")
    font_subtitle = ctk.CTkFont(family="Segoe UI", size=13)
    font_section = ctk.CTkFont(family="Segoe UI Semibold", size=13, weight="bold")
    font_body = ctk.CTkFont(family="Segoe UI", size=13)
    font_small = ctk.CTkFont(family="Segoe UI", size=11)
    font_mono = ctk.CTkFont(family="Consolas", size=12)
    font_btn = ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold")

    selected_files: list[Path] = []
    fmt_var = tk.StringVar(value="Word  (.docx)")
    outdir_var = tk.StringVar(value="")

    container = ctk.CTkFrame(root, fg_color="transparent")
    container.pack(fill="both", expand=True, padx=28, pady=24)

    # --- Header ------------------------------------------------------------- #
    header = ctk.CTkFrame(container, fg_color="transparent")
    header.pack(fill="x", pady=(0, 18))
    ctk.CTkLabel(header, text="Markdown Converter", font=font_title,
                 anchor="w").pack(anchor="w")
    ctk.CTkLabel(header, text="Turn your .md notes into shareable Word or PDF documents.",
                 font=font_subtitle, text_color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

    # The footer holds the controls + Convert button. It is packed to the
    # bottom FIRST so it is always reserved and visible; the file list (packed
    # afterwards with expand) only takes the leftover space above it.
    footer = ctk.CTkFrame(container, fg_color="transparent")
    footer.pack(side="bottom", fill="x")

    # --- Files card --------------------------------------------------------- #
    files_card = ctk.CTkFrame(container, fg_color=CARD, corner_radius=14,
                              border_width=1, border_color=BORDER)
    files_card.pack(fill="both", expand=True)

    files_head = ctk.CTkFrame(files_card, fg_color="transparent")
    files_head.pack(fill="x", padx=18, pady=(16, 6))
    ctk.CTkLabel(files_head, text="Files", font=font_section).pack(side="left")
    count_label = ctk.CTkLabel(files_head, text="0 selected", font=font_small,
                               text_color=MUTED)
    count_label.pack(side="left", padx=(8, 0))

    def add_files():
        paths = filedialog.askopenfilenames(
            title="Select Markdown files",
            filetypes=[("Markdown", "*.md *.markdown"), ("All files", "*.*")],
        )
        for p in paths:
            pp = Path(p)
            if pp not in selected_files:
                selected_files.append(pp)
        refresh_list()

    def clear_all():
        selected_files.clear()
        refresh_list()

    ctk.CTkButton(files_head, text="Clear all", width=80, height=30,
                  font=font_body, fg_color="transparent", text_color=MUTED,
                  hover_color=SURFACE, border_width=1, border_color=BORDER,
                  command=clear_all).pack(side="right")
    ctk.CTkButton(files_head, text="+  Add files", width=110, height=30,
                  font=font_body, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                  command=add_files).pack(side="right", padx=(0, 8))

    file_list = ctk.CTkScrollableFrame(files_card, fg_color=SURFACE,
                                       corner_radius=10)
    file_list.pack(fill="both", expand=True, padx=18, pady=(6, 18))

    def remove_file(path: Path):
        if path in selected_files:
            selected_files.remove(path)
        refresh_list()

    def refresh_list():
        for child in file_list.winfo_children():
            child.destroy()
        count_label.configure(
            text=f"{len(selected_files)} selected" if selected_files else "0 selected")
        if not selected_files:
            ctk.CTkLabel(
                file_list,
                text="No files yet.\nClick “Add files” to choose your .md documents.",
                font=font_body, text_color=MUTED, justify="center").pack(pady=40)
            return
        for path in selected_files:
            row = ctk.CTkFrame(file_list, fg_color=CARD, corner_radius=8)
            row.pack(fill="x", pady=3, padx=2)
            ctk.CTkLabel(row, text="📄", font=font_body).pack(side="left", padx=(10, 4), pady=8)
            name = ctk.CTkLabel(row, text=path.name, font=font_body, anchor="w")
            name.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=str(path.parent), font=font_small,
                         text_color=MUTED, anchor="e").pack(side="left", padx=8)
            ctk.CTkButton(row, text="✕", width=28, height=28, font=font_body,
                          fg_color="transparent", text_color=MUTED,
                          hover_color=("#fee2e2", "#3a1f1f"),
                          command=lambda p=path: remove_file(p)).pack(side="right", padx=8)

    # --- Options row (format + output) ------------------------------------- #
    options = ctk.CTkFrame(footer, fg_color="transparent")
    options.pack(fill="x", pady=(16, 0))
    options.grid_columnconfigure(0, weight=0)
    options.grid_columnconfigure(1, weight=1)

    fmt_box = ctk.CTkFrame(options, fg_color=CARD, corner_radius=14,
                           border_width=1, border_color=BORDER)
    fmt_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    ctk.CTkLabel(fmt_box, text="Output format", font=font_section).pack(
        anchor="w", padx=16, pady=(14, 8))
    ctk.CTkSegmentedButton(
        fmt_box, values=["Word  (.docx)", "PDF  (.pdf)"], variable=fmt_var,
        font=font_body, height=34, selected_color=ACCENT,
        selected_hover_color=ACCENT_HOVER).pack(
        fill="x", padx=16, pady=(0, 16))

    out_box = ctk.CTkFrame(options, fg_color=CARD, corner_radius=14,
                           border_width=1, border_color=BORDER)
    out_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    ctk.CTkLabel(out_box, text="Save to folder", font=font_section).pack(
        anchor="w", padx=16, pady=(14, 8))
    out_row = ctk.CTkFrame(out_box, fg_color="transparent")
    out_row.pack(fill="x", padx=16, pady=(0, 4))
    out_entry = ctk.CTkEntry(out_row, textvariable=outdir_var, font=font_body,
                             height=34, placeholder_text="Default: next to each source file")
    out_entry.pack(side="left", fill="x", expand=True)

    def choose_outdir():
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            outdir_var.set(d)

    ctk.CTkButton(out_row, text="Browse", width=80, height=34, font=font_body,
                  fg_color="transparent", text_color=ACCENT, border_width=1,
                  border_color=ACCENT, hover_color=SURFACE,
                  command=choose_outdir).pack(side="left", padx=(8, 0))
    ctk.CTkLabel(out_box, text="Leave empty to save each file beside its original.",
                 font=font_small, text_color=MUTED, anchor="w").pack(
        anchor="w", padx=16, pady=(0, 16))

    # --- Status log --------------------------------------------------------- #
    log = ctk.CTkTextbox(footer, height=96, font=font_mono,
                         fg_color=CARD, border_width=1, border_color=BORDER,
                         corner_radius=12, wrap="word")
    log.pack(fill="x", expand=False, pady=(16, 0))
    log.configure(state="disabled")

    def log_write(line: str):
        log.configure(state="normal")
        log.insert("end", line + "\n")
        log.see("end")
        log.configure(state="disabled")
        root.update_idletasks()

    # --- Convert button ----------------------------------------------------- #
    def fmt_value() -> str:
        return "docx" if fmt_var.get().lower().startswith("word") else "pdf"

    def do_convert():
        if not selected_files:
            messagebox.showwarning("No files", "Please add at least one .md file.")
            return
        fmt = fmt_value()
        outdir = Path(outdir_var.get()) if outdir_var.get().strip() else None

        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        log_write(f"Converting {len(selected_files)} file(s) to {fmt.upper()} ...")

        def progress(i, total, name, ok, message):
            status = "OK  " if ok else "FAIL"
            log_write(f"[{i}/{total}] {status} {name}"
                      + (f"  ->  {message}" if ok else f"   ({message})"))

        convert_btn.configure(state="disabled", text="Converting ...")
        try:
            successes, failures = convert_many(selected_files, fmt, outdir, progress)
        except Exception as exc:  # noqa: BLE001
            log_write(f"Unexpected error: {exc}")
            convert_btn.configure(state="normal", text="Convert")
            return
        convert_btn.configure(state="normal", text="Convert")

        log_write(f"\nDone. {len(successes)} succeeded, {len(failures)} failed.")
        if failures:
            messagebox.showwarning(
                "Finished with errors",
                f"{len(successes)} succeeded, {len(failures)} failed.\nSee the status log.")
        else:
            messagebox.showinfo("Success", f"All {len(successes)} file(s) converted.")
            target = str(outdir) if outdir else "next to each source file"
            log_write(f"Saved to: {target}")

    convert_btn = ctk.CTkButton(footer, text="Convert", font=font_btn,
                                height=46, corner_radius=12, fg_color=ACCENT,
                                hover_color=ACCENT_HOVER, command=do_convert)
    convert_btn.pack(fill="x", pady=(16, 0))

    refresh_list()
    root.mainloop()
    return 0


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Markdown files to DOCX or PDF.")
    parser.add_argument("files", nargs="*",
                        help="Markdown files, globs, or folders. "
                             "If omitted, the GUI opens.")
    parser.add_argument("-f", "--format", choices=["docx", "pdf"], default="docx",
                        help="Output format (default: docx).")
    parser.add_argument("-o", "--outdir", default=None,
                        help="Output folder (default: next to each source file).")
    parser.add_argument("--gui", action="store_true", help="Force the GUI.")
    args = parser.parse_args(argv)

    if args.gui or not args.files:
        return run_gui()
    return run_cli(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
