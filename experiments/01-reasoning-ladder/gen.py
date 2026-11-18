"""Generate graded tasks with exact answers: mult, trace, logic."""
from __future__ import annotations

import itertools
import json
import random
import sys
from typing import Any

rng = random.Random(20261116)
NAMES = ["Ana", "Ben", "Cal", "Dee", "Eli", "Fay", "Gus", "Hal", "Ivy", "Jon", "Kim", "Lou", "Max"]


def mult(n: int) -> dict[str, Any]:
    a = rng.randint(10 ** (n - 1), 10**n - 1)
    b = rng.randint(10 ** (n - 1), 10**n - 1)
    return {
        "problem": f"Compute the exact product {a} × {b}. The answer is a single integer with no commas.",
        "answer": str(a * b),
    }


def trace(k: int) -> dict[str, Any]:
    v = "abcd"
    lines = ["a, b, c, d = 3, 7, 2, 5"]
    for _ in range(k):
        x, y = rng.sample(v, 2)
        m = rng.choice([17, 23, 31, 47])
        t = rng.randint(1, 9)
        op = rng.choice(["add", "mul", "sub", "swap", "if"])
        if op == "add":
            lines.append(f"{x} = ({x} + {t} * {y}) % {m}")
        elif op == "mul":
            lines.append(f"{x} = ({x} * {y} + {t}) % {m}")
        elif op == "sub":
            lines.append(f"{x} = ({x} - {y}) % {m}")
        elif op == "swap":
            lines.append(f"{x}, {y} = {y}, {x}")
        else:
            z = rng.choice([c for c in v if c not in (x, y)])
            lines.append(f"if {x} > {y}:\n    {z} = ({z} + {t}) % {m}\nelse:\n    {x} = ({x} + {y}) % {m}")
    code = "\n".join(lines)
    env: dict[str, int] = {}
    exec(code, {}, env)
    return {
        "problem": (
            "Execute this Python code mentally (Python semantics; % always returns a non-negative result here) "
            "and give the final values of a, b, c, d.\n\n```python\n" + code + "\n```\n\n"
            "Answer format: four integers separated by commas, in order a,b,c,d."
        ),
        "answer": ",".join(str(env[c]) for c in v),
    }


def _holds(c: tuple, pos: dict[str, int]) -> bool:
    kind = c[0]
    if kind == "left":
        return pos[c[1]] < pos[c[2]]
    if kind == "adj":
        return abs(pos[c[1]] - pos[c[2]]) == 1
    if kind == "notadj":
        return abs(pos[c[1]] - pos[c[2]]) != 1
    if kind == "notpos":
        return pos[c[1]] != c[2]
    if kind == "dist":
        return abs(pos[c[1]] - pos[c[2]]) == c[3]
    raise ValueError(kind)


def _text(c: tuple) -> str:
    k = c[0]
    if k == "left":
        return f"{c[1]} sits somewhere to the left of {c[2]}."
    if k == "adj":
        return f"{c[1]} sits directly next to {c[2]}."
    if k == "notadj":
        return f"{c[1]} does not sit next to {c[2]}."
    if k == "notpos":
        return f"{c[1]} is not in seat {c[2]}."
    return f"There are exactly {c[3] - 1} people between {c[1]} and {c[2]}."


def count(names: list[str], clues: list[tuple], cap: int = 2) -> int:
    """Count seatings satisfying clues, stopping at cap. Backtracking, most-constrained person first."""
    n = len(names)
    deg = {p: 0 for p in names}
    for c in clues:
        deg[c[1]] += 1
        if c[0] != "notpos":
            deg[c[2]] += 1
    order = sorted(names, key=lambda p: -deg[p])
    rank = {p: r for r, p in enumerate(order)}
    checks: list[list[tuple]] = [[] for _ in range(n)]
    for c in clues:  # check each clue as soon as everyone it mentions is seated
        r = rank[c[1]] if c[0] == "notpos" else max(rank[c[1]], rank[c[2]])
        checks[r].append(c)
    pos: dict[str, int] = {}
    used = [False] * (n + 1)
    found = 0

    def rec(r: int) -> bool:
        nonlocal found
        if r == n:
            found += 1
            return found >= cap
        p = order[r]
        for s in range(1, n + 1):
            if used[s]:
                continue
            pos[p] = s
            if all(_holds(c, pos) for c in checks[r]):
                used[s] = True
                if rec(r + 1):
                    return True
                used[s] = False
        pos.pop(p, None)
        return False

    rec(0)
    return found


def logic(n: int) -> dict[str, Any]:
    if n > 8:
        return logic_big(n)
    names = NAMES[:n]
    hidden = names[:]
    rng.shuffle(hidden)
    pos = {p: i + 1 for i, p in enumerate(hidden)}
    perms = [dict(zip(p, range(1, n + 1))) for p in itertools.permutations(names)]

    def rand_clue() -> tuple:
        while True:
            x, y = rng.sample(names, 2)
            k = rng.choice(["left", "left", "adj", "notadj", "notpos", "dist"])
            c: tuple = (k, x, y) if k != "notpos" else (k, x, rng.randint(1, n))
            if k == "dist":
                c = (k, x, y, abs(pos[x] - pos[y]))
            if _holds(c, pos):
                return c

    clues: list[tuple] = []
    live = perms
    while len(live) > 1:
        c = rand_clue()
        nxt = [p for p in live if _holds(c, p)]
        if len(nxt) < len(live):
            clues.append(c)
            live = nxt
    for c in list(clues):  # drop redundant clues to make the puzzle tighter
        rest = [d for d in clues if d is not c]
        if sum(all(_holds(d, p) for d in rest) for p in perms) == 1:
            clues = rest
    rng.shuffle(clues)
    body = "\n".join(f"{i + 1}. {_text(c)}" for i, c in enumerate(clues))
    return {
        "problem": (
            f"{n} people ({', '.join(names)}) sit in a row of seats numbered 1 to {n}, left to right. "
            f"Exactly one arrangement satisfies all clues:\n\n{body}\n\n"
            "Answer format: the names in seat order 1..N, separated by commas."
        ),
        "answer": ",".join(hidden),
    }


def logic_big(n: int) -> dict[str, Any]:
    """Same puzzle as logic(), for n > 8 where enumerating every permutation is too slow."""
    names = NAMES[:n]
    hidden = names[:]
    rng.shuffle(hidden)
    pos = {p: i + 1 for i, p in enumerate(hidden)}

    def rand_clue() -> tuple:
        while True:
            x, y = rng.sample(names, 2)
            k = rng.choice(["left", "left", "adj", "notadj", "notpos", "dist"])
            c: tuple = (k, x, y) if k != "notpos" else (k, x, rng.randint(1, n))
            if k == "dist":
                c = (k, x, y, abs(pos[x] - pos[y]))
            if _holds(c, pos):
                return c

    clues: list[tuple] = []
    while count(names, clues) > 1:
        clues.append(rand_clue())
    for c in list(clues):  # drop redundant clues to make the puzzle tighter
        rest = [d for d in clues if d is not c]
        if count(names, rest) == 1:
            clues = rest
    rng.shuffle(clues)
    body = "\n".join(f"{i + 1}. {_text(c)}" for i, c in enumerate(clues))
    return {
        "problem": (
            f"{n} people ({', '.join(names)}) sit in a row of seats numbered 1 to {n}, left to right. "
            f"Exactly one arrangement satisfies all clues:\n\n{body}\n\n"
            "Answer format: the names in seat order 1..N, separated by commas."
        ),
        "answer": ",".join(hidden),
    }


LEVELS = {"mult": [4, 6, 8, 10, 12], "trace": [10, 20, 40, 80, 160], "logic": [4, 5, 6, 7, 8]}
LEVELS2 = {"mult": [16, 20, 25, 32, 40], "trace": [250, 400, 600, 900, 1300], "logic": [9, 10, 11, 12, 13]}
GEN = {"mult": mult, "trace": trace, "logic": logic}

if __name__ == "__main__":
    stage2 = len(sys.argv) > 2 and sys.argv[2] == "2"
    if stage2:
        rng.seed(20261117)
    tasks = []
    for fam, lv in (LEVELS2 if stage2 else LEVELS).items():
        for i, n in enumerate(lv):
            t = GEN[fam](n)
            lvl = i + 1 + (5 if stage2 else 0)
            tasks.append({"id": f"{fam}-L{lvl}", "family": fam, "level": lvl, "param": n, **t})
    json.dump(tasks, open(sys.argv[1], "w"), indent=1)
    for t in tasks:
        print(t["id"], t["param"], len(t["problem"]), t["answer"][:40])
