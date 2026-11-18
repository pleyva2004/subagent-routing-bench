"""Build the web version of the paper (docs/index.html) and publish the PDF (docs/paper.pdf).

The web page is generated from the same LaTeX sources as the PDF:
- each TikZ/pgfplots figure is compiled on its own and converted to SVG, so the charts match the PDF;
- figure, table and section numbers are read from main.aux, so cross-references match the PDF;
- pandoc converts the text, with citations formatted from references.bib.

Run after `latexmk -pdf main.tex` (main.aux must be current):
    python3 paper/build_web.py
Needs pdflatex (with pgfplots), pdftocairo (poppler) and pandoc.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

PAPER = Path(__file__).resolve().parent
ROOT = PAPER.parent
DOCS = ROOT / "docs"
BUILD = PAPER / "web-build"
FIG_OUT = DOCS / "assets" / "figures"

# The paper's text width (A4 with 1in margins), so standalone figures size like they do in the PDF.
STANDALONE = r"""\documentclass[border=6pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{xcolor}
\definecolor{arxivblue}{HTML}{1F4E79}
\definecolor{arxivgray}{HTML}{4D4D4D}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,shapes.geometric,calc}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\begin{document}
\setlength{\linewidth}{159.2mm}%
\input{../figures/FIGURE_NAME}
\end{document}
"""


def run(cmd: list[str], cwd: Path) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")


def figures() -> list[str]:
    names = sorted(p.stem for p in (PAPER / "figures").glob("*.tex"))
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        tex = BUILD / f"fig-{name}.tex"
        tex.write_text(STANDALONE.replace("FIGURE_NAME", name))
        run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex.name], cwd=BUILD)
        run(["pdftocairo", "-svg", f"fig-{name}.pdf", str(FIG_OUT / f"paper-{name}.svg")], cwd=BUILD)
    return names


def labels() -> dict[str, str]:
    aux = (PAPER / "main.aux").read_text(errors="replace")
    return {m.group(1): m.group(2) for m in re.finditer(r"\\newlabel\{([^}]*)\}\{\{([^}]*)\}", aux)}


def inline_inputs(text: str) -> str:
    """Expand \\input of text files; turn figure inputs into SVG images."""
    def expand(m: re.Match[str]) -> str:
        name = m.group(1)
        if name.startswith("figures/"):
            return rf"\includegraphics{{assets/figures/paper-{Path(name).name}.svg}}"
        path = PAPER / (name if name.endswith(".tex") else f"{name}.tex")
        return inline_inputs(path.read_text())
    return re.sub(r"\\input\{([^}]*)\}", expand, text)


def prepare(text: str, nums: dict[str, str]) -> str:
    body = text[text.index(r"\begin{document}"):]
    body = inline_inputs(body)
    # Number captions the way LaTeX does ("Figure 2:", "Table 3:").
    def caption_env(m: re.Match[str]) -> str:
        env, block = m.group(1), m.group(0)
        label = re.search(r"\\label\{([^}]*)\}", block)
        if label and label.group(1) in nums:
            kind = "Figure" if env == "figure" else "Table"
            block = block.replace(r"\caption{", rf"\caption{{\textbf{{{kind} {nums[label.group(1)]}:}} ", 1)
        return block
    body = re.sub(r"\\begin\{(figure|table)\}.*?\\end\{\1\}", caption_env, body, flags=re.S)
    body = re.sub(r"\\ref\{([^}]*)\}", lambda m: nums.get(m.group(1), "??"), body)
    body = re.sub(r"\\paragraph\{([^}]*)\}", r"\\textbf{\1}", body)  # keep the run-in headings
    body = re.sub(r"\\begin\{tabular\}\{([^\n]*)\}", lambda m: r"\begin{tabular}{" + m.group(1).replace("L{", "p{") + "}", body)
    body = body.replace(r"\maketitle", "")
    return "\\documentclass{article}\n" + body


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    names = figures()
    nums = labels()
    (BUILD / "paper-web.tex").write_text(prepare((PAPER / "main.tex").read_text(), nums))
    run(["pandoc", "paper-web.tex", "-f", "latex", "-t", "html5", "-s",
         "--citeproc", "--bibliography", str(PAPER / "references.bib"),
         "--mathml", "--number-sections",
         "-M", "title=Routing Claude Code Sub-Agents by Model and Effort: A Case Study",
         "-M", "author=Pablo Leyva",
         "-M", "reference-section-title=References", "-M", "link-citations=true",
         "-M", "document-css=false",
         "--css", "assets/paper.css",
         "-B", str(PAPER / "web-header.html"),
         "-o", str(DOCS / "index.html")], cwd=BUILD)
    shutil.copyfile(PAPER / "main.pdf", DOCS / "paper.pdf")
    print(f"built docs/index.html, docs/paper.pdf and {len(names)} figures ({', '.join(names)})")


if __name__ == "__main__":
    main()
