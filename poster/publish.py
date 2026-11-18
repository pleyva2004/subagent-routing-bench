"""Build the one-page poster and publish it to the GitHub Pages site.

Writes docs/poster.pdf and docs/assets/poster.svg (shown by docs/poster.html).
Run from anywhere:  python3 poster/publish.py
Needs pdflatex (with pgfplots and extsizes), latexmk and pdftocairo (poppler).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

POSTER = Path(__file__).resolve().parent
ROOT = POSTER.parent
DOCS = ROOT / "docs"


def run(cmd: list[str], cwd: Path) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}")


def main() -> None:
    run(["python3", str(ROOT / "analysis" / "make_poster_figures.py")], cwd=ROOT)
    run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"], cwd=POSTER)
    pages = subprocess.run(["pdfinfo", "main.pdf"], cwd=POSTER, capture_output=True, text=True).stdout
    count = next((line.split()[-1] for line in pages.splitlines() if line.startswith("Pages:")), "?")
    if count != "1":
        raise SystemExit(f"the poster must be one page; it is {count}")
    shutil.copyfile(POSTER / "main.pdf", DOCS / "poster.pdf")
    (DOCS / "assets").mkdir(exist_ok=True)
    run(["pdftocairo", "-svg", str(DOCS / "poster.pdf"), str(DOCS / "assets" / "poster.svg")], cwd=ROOT)
    print("built docs/poster.pdf and docs/assets/poster.svg (1 page)")


if __name__ == "__main__":
    main()
