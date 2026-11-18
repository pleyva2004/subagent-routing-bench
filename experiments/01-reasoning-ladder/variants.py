"""Re-run trace-L3 under plausible misreadings to see which one yields Haiku's answer."""
import json, re
t = [x for x in json.load(open("tasks.json")) if x["id"] == "trace-L3"][0]
code = re.search(r"```python\n(.*?)\n```", t["problem"], re.S).group(1)
def run(src):
    env = {}
    exec(src, {}, env)
    return ",".join(str(env[c]) for c in "abcd")
print("truth           ", run(code))
# sequential swap: x, y = y, x  ->  x = y; y = x
print("sequential swap ", run(re.sub(r"^(\w), (\w) = (\w), (\w)$", r"\1 = \3\n\2 = \4", code, flags=re.M)))
# precedence: (x + t * y) read as ((x + t) * y)
print("add precedence  ", run(re.sub(r"\((\w) \+ (\d) \* (\w)\)", r"((\1 + \2) * \3)", code)))
# if/else: else-branch skipped
print("skip else       ", run(re.sub(r"\nelse:\n    .*", "", code)))
# if: strict > read as >=
print("> as >=         ", run(code.replace(" > ", " >= ")))
# find each prefix length whose state matches Haiku's final answer, to locate an early stop
lines = code.split("\n")
