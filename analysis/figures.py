"""Render the five benchmark figures into docs/assets/figures/.

Inputs:
  experiments/01-reasoning-ladder/{tasks,tasks2}.json, results.jsonl
  data/coding/costs.json

Run from the repo root:
  uv run --with matplotlib python analysis/figures.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LADDER_DIR = ROOT / "experiments" / "01-reasoning-ladder"
COSTS_PATH = ROOT / "data" / "coding" / "costs.json"
OUT_DIR = ROOT / "docs" / "assets" / "figures"

SONNET_COLOR = "#0072B2"
HAIKU_COLOR = "#E69F00"
MODEL_COLORS = {"haiku": HAIKU_COLOR, "sonnet": SONNET_COLOR}
MODEL_NAMES = {"haiku": "Haiku", "sonnet": "Sonnet"}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
LADDER_EFFORTS = ["low", "medium", "high", "xhigh"]
DPI = 150
TEXT_COLOR = "#222222"
MUTED_COLOR = "#555555"

plt.rcParams.update(
    {
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.edgecolor": MUTED_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "legend.frameon": False,
    }
)


def model_key(raw: str) -> str:
    """Map 'claude-haiku-5-5' or 'haiku' to 'haiku'; same for sonnet."""
    for key in ("haiku", "sonnet"):
        if key in raw:
            return key
    raise ValueError(f"unknown model: {raw}")


def config_label(model: str, effort: str) -> str:
    return f"{MODEL_NAMES[model]} {effort}"


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save(fig: plt.Figure, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")


# ---------------------------------------------------------------- figure 1


def load_trace_params() -> Dict[int, int]:
    """Map trace level -> statement count, merged from both task files."""
    params: Dict[int, int] = {}
    for name in ("tasks.json", "tasks2.json"):
        for task in load_json(LADDER_DIR / name):  # type: ignore[union-attr]
            if task["family"] == "trace":
                params[int(task["level"])] = int(task["param"])
    return params


def load_trace_status() -> Dict[Tuple[str, str], Dict[int, str]]:
    """Map (model, effort) -> {trace level: status}. Later rows overwrite earlier ones."""
    status: Dict[Tuple[str, str], Dict[int, str]] = {}
    with (LADDER_DIR / "results.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row["family"] != "trace":
                continue
            key = (model_key(row["model"]), row["effort"])
            status.setdefault(key, {})[int(row["level"])] = row["status"]
    return status


def summarize_ladder(levels: List[int], statuses: Dict[int, str]) -> Tuple[int, int]:
    """Return (longest level passed before the first non-pass, longest level passed at all).

    A missing or "skipped" level counts as not passed. Returns 0 when nothing passed.
    """
    before = 0
    for level in levels:
        if statuses.get(level) != "pass":
            break
        before = level
    passed = [level for level in levels if statuses.get(level) == "pass"]
    return before, max(passed) if passed else 0


def plot_reasoning_trace() -> None:
    params = load_trace_params()
    status = load_trace_status()
    levels = sorted(params)
    configs = [(m, e) for m in ("haiku", "sonnet") for e in LADDER_EFFORTS]

    bar_h = 0.38
    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    rows: List[Tuple[str, int, int, int, int]] = []
    for i, (model, effort) in enumerate(configs):
        before, longest = summarize_ladder(levels, status.get((model, effort), {}))
        before_p = params[before] if before else 0
        longest_p = params[longest] if longest else 0
        rows.append((config_label(model, effort), before, before_p, longest, longest_p))
        color = MODEL_COLORS[model]
        ax.barh(i - bar_h / 2, before_p, height=bar_h, color=color)
        ax.barh(i + bar_h / 2, longest_p, height=bar_h, color=color, alpha=0.35)

    pad = max(params.values()) * 0.012
    for i, (_, before, before_p, longest, longest_p) in enumerate(rows):
        ax.text(before_p + pad, i - bar_h / 2, f"{before_p}  (L{before})", va="center", fontsize=9)
        ax.text(longest_p + pad, i + bar_h / 2, f"{longest_p}  (L{longest})", va="center", fontsize=9)

    ax.set_yticks(range(len(configs)))
    ax.set_yticklabels([row[0] for row in rows])
    ax.set_ylim(len(configs) - 0.5, -0.5)
    ax.set_xlim(0, max(params.values()) * 1.2)
    ax.set_xlabel("Trace length (statements executed)")
    ax.set_title("Reasoning ladder: longest trace solved per config")
    ax.grid(axis="x", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[
            Patch(facecolor=HAIKU_COLOR, label="Haiku"),
            Patch(facecolor=SONNET_COLOR, label="Sonnet"),
            Patch(facecolor=MUTED_COLOR, label="Before first non-pass (solid)"),
            Patch(facecolor=MUTED_COLOR, alpha=0.35, label="Longest solved at all (light)"),
        ],
        loc="upper right",  # the top rows (Haiku) are short, so this corner is empty
        fontsize=9,
    )
    print("figure 1 (statements, level):")
    for label, before, before_p, longest, longest_p in rows:
        print(f"  {label:<14} before={before_p:>5} (L{before})  longest={longest_p:>5} (L{longest})")
    save(fig, "reasoning_trace.png")


# -------------------------------------------------------- coding costs


def load_costs() -> Dict[str, dict]:
    return load_json(COSTS_PATH)  # type: ignore[return-value]


def costs_for_set(costs: Dict[str, dict], set_name: str) -> List[dict]:
    """Entries for one task set, ordered Haiku then Sonnet, efforts low -> max."""
    entries = [v for v in costs.values() if v["set"] == set_name]

    def sort_key(entry: dict) -> Tuple[int, int]:
        model, effort = entry["config"].split(":")
        return (0 if model == "haiku" else 1, EFFORTS.index(effort))

    return sorted(entries, key=sort_key)


def entry_model_effort(entry: dict) -> Tuple[str, str]:
    model, effort = entry["config"].split(":")
    return model, effort


def plot_easy_cost_per_success() -> None:
    entries = costs_for_set(load_costs(), "easy")
    labels = [config_label(*entry_model_effort(e)) for e in entries]
    values = [e["cost_usd_per_pass"] for e in entries]
    colors = [MODEL_COLORS[entry_model_effort(e)[0]] for e in entries]

    fig, ax = plt.subplots(figsize=(9, 6.5))
    y = range(len(entries))
    ax.barh(y, values, color=colors, height=0.65)
    for i, entry in enumerate(entries):
        ax.text(
            values[i] * 1.12,
            i,
            f"${values[i]:.4f}  ({entry['passes']}/{entry['runs']} passes)",
            va="center",
            fontsize=9,
        )

    ax.set_xscale("log")
    ax.set_xlim(0.01, 10)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.set_ylim(len(entries) - 0.5, -0.5)
    ax.set_xlabel("Cost per pass (USD, log scale)")
    ax.set_title("Easy set: cost per pass by config")
    ax.grid(axis="x", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[Patch(facecolor=HAIKU_COLOR, label="Haiku"), Patch(facecolor=SONNET_COLOR, label="Sonnet")],
        loc="upper right",  # the cheap top rows leave this corner empty
    )
    save(fig, "easy_cost_per_success.png")


def plot_effort_cost_curve() -> None:
    entries = costs_for_set(load_costs(), "easy")
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for model in ("haiku", "sonnet"):
        pts = [
            (EFFORTS.index(entry_model_effort(e)[1]), e["cost_usd_per_pass"])
            for e in entries
            if entry_model_effort(e)[0] == model
        ]
        pts.sort()
        ax.plot(
            [p[0] for p in pts],
            [p[1] for p in pts],
            marker="o",
            markersize=7,
            linewidth=2.2,
            color=MODEL_COLORS[model],
            label=MODEL_NAMES[model],
        )

    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(range(len(EFFORTS)))
    ax.set_xticklabels(EFFORTS)
    ax.set_xlabel("Reasoning effort")
    ax.set_ylabel("Cost per pass (USD, log scale)")
    ax.set_title("Easy set: cost per pass vs. reasoning effort")
    ax.grid(axis="y", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left")
    save(fig, "effort_cost_curve.png")


# ----------------------------------------------------------- hard set


def plot_hard_pass_rates() -> None:
    entries = costs_for_set(load_costs(), "hard")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for i, entry in enumerate(entries):
        model, effort = entry_model_effort(entry)
        rate = entry["passes"] / entry["runs"]
        lo, hi = entry["pass_rate_95ci"]
        color = MODEL_COLORS[model]
        ax.errorbar(
            i,
            rate,
            yerr=[[rate - lo], [hi - rate]],
            fmt="o",
            markersize=9,
            color=color,
            ecolor=color,
            elinewidth=1.8,
            capsize=5,
        )
        ax.text(i + 0.12, rate, f"{entry['passes']}/{entry['runs']}", va="center", fontsize=9)

    ax.set_xticks(range(len(entries)))
    ax.set_xticklabels([config_label(*entry_model_effort(e)) for e in entries])
    ax.set_xlim(-0.5, len(entries) - 0.5)
    ax.set_ylim(0.5, 1.0)
    ax.set_xlabel("Config")
    ax.set_ylabel("Pass rate (passes / runs), 95% CI")
    ax.set_title("Hard set: pass rate by config")
    ax.grid(axis="y", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[Patch(facecolor=HAIKU_COLOR, label="Haiku"), Patch(facecolor=SONNET_COLOR, label="Sonnet")],
        loc="lower left",
    )
    save(fig, "hard_pass_rates.png")


# Label placement (offset in points, horizontal alignment). Sonnet low and medium sit close together.
LABEL_OFFSETS = {
    "haiku:low": (8, 4, "left"),
    "sonnet:low": (-8, -12, "right"),
    "sonnet:medium": (8, 6, "left"),
    "sonnet:high": (8, -4, "left"),
    "sonnet:xhigh": (-8, 8, "right"),
}


def plot_hard_cost_vs_time() -> None:
    entries = costs_for_set(load_costs(), "hard")
    fig, ax = plt.subplots(figsize=(9, 6))
    for entry in entries:
        model, effort = entry_model_effort(entry)
        x = entry["agent_seconds_per_run"]
        y = entry["cost_usd_per_pass"]
        ax.scatter(x, y, s=90, color=MODEL_COLORS[model], zorder=3)
        dx, dy, ha = LABEL_OFFSETS.get(f"{model}:{effort}", (8, 4, "left"))
        ax.annotate(
            config_label(model, effort),
            (x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            ha=ha,
            fontsize=10,
        )

    ax.set_xlim(0, 170)
    ax.set_ylim(0, 0.6)
    ax.set_xlabel("Agent seconds per run")
    ax.set_ylabel("Cost per pass (USD)")
    ax.set_title("Hard set: cost per pass vs. time per run")
    ax.grid(color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[Patch(facecolor=HAIKU_COLOR, label="Haiku"), Patch(facecolor=SONNET_COLOR, label="Sonnet")],
        loc="upper left",
    )
    save(fig, "hard_cost_vs_time.png")


def main() -> None:
    plot_reasoning_trace()
    plot_easy_cost_per_success()
    plot_effort_cost_curve()
    plot_hard_pass_rates()
    plot_hard_cost_vs_time()


if __name__ == "__main__":
    main()
