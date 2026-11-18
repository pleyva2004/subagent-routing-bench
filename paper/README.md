# Paper

The paper version of the study, in LaTeX. The compiled PDF is published at `docs/paper.pdf`.

## Build

```
cd paper && latexmk -pdf main.tex
```

pdfLaTeX and BibTeX. Clean with `latexmk -C`.

## Figures

The charts in `figures/` are pgfplots code generated from the data, so they stay in sync with `data/`:

```
python3 analysis/make_tikz_figures.py
```

`figures/pipeline.tex` is hand-written TikZ.

## Layout

- `main.tex`: preamble, title block and section order.
- `abstract.tex`, `sections/01-introduction.tex` to `sections/06-conclusion.tex`: the text.
- `references.bib`: the bibliography (plain style).
- `arxiv-style.sty`: the single-column preprint layout.
