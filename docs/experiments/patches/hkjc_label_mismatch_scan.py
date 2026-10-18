"""HKJC 9D label-mismatch scan.

1. AST: every `"kw" in X` (and `any(k in X for k in (...))`) in the engine; resolve X to the Logic
   field(s) it reads via _text/_value/_clean/.get("field") (one level of local-variable indirection).
2. Corpus: count, per (field, keyword), how many stored runners contain the keyword; list each field's
   real label vocabulary so a 0-hit keyword can be matched to the label Facts actually writes.
"""
import ast, glob, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(sys.argv[1])
ENGINE = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine"
ROOT = Path(open(REPO / ".wongchoi_hk_data_root").read().strip())
ACCESSORS = {"_text", "_value", "_clean", "get"}


def fields_in(node):
    """String constants passed to accessor calls anywhere inside node."""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
            if name in ACCESSORS:
                for a in sub.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and re.fullmatch(r"[a-z][a-z0-9_]+", a.value):
                        out.add(a.value)
    return out


checks = []
for path in sorted(list(ENGINE.glob("*.py")) + list(ENGINE.glob("features/*.py"))):
    if path.name in ("renderer.py",):  # display-only; scanned separately below
        pass
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        var_fields = defaultdict(set)
        for n in ast.walk(func):
            if isinstance(n, ast.Assign):
                f = fields_in(n.value)
                # propagate one level: x = some_func(y) where y already mapped
                for sub in ast.walk(n.value):
                    if isinstance(sub, ast.Name) and sub.id in var_fields:
                        f |= var_fields[sub.id]
                for t in n.targets:
                    for nm in ast.walk(t):
                        if isinstance(nm, ast.Name):
                            var_fields[nm.id] |= f

        def resolve(expr):
            f = fields_in(expr)
            for sub in ast.walk(expr):
                if isinstance(sub, ast.Name) and sub.id in var_fields:
                    f |= var_fields[sub.id]
            return f

        for n in ast.walk(func):
            if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.In) \
                    and isinstance(n.left, ast.Constant) and isinstance(n.left.value, str):
                kw = n.left.value
                if len(kw) < 1 or kw in ("/", "→", "|"):
                    continue
                checks.append(dict(file=path.name, func=func.name, line=n.lineno, kw=kw,
                                   fields=sorted(resolve(n.comparators[0])), expr=ast.unparse(n.comparators[0])[:60]))
            if isinstance(n, ast.GeneratorExp) and isinstance(n.elt, ast.Compare) and isinstance(n.elt.ops[0], ast.In):
                it = n.generators[0].iter
                if isinstance(it, (ast.Tuple, ast.List, ast.Set)):
                    for e in it.elts:
                        if isinstance(e, ast.Constant) and isinstance(e.value, str):
                            checks.append(dict(file=path.name, func=func.name, line=n.lineno, kw=e.value,
                                               fields=sorted(resolve(n.elt.comparators[0])), expr=ast.unparse(n.elt.comparators[0])[:60]))

# ---------- corpus
values = defaultdict(list)  # field -> list of str values (non-empty)
n_runners = 0
for lf in glob.glob(str(ROOT / "20*_*" / "Race_*_Logic.json")):
    try:
        logic = json.load(open(lf, encoding="utf-8"))
    except Exception:
        continue
    for h in (logic.get("horses") or {}).values():
        if not isinstance(h, dict):
            continue
        n_runners += 1
        data = h.get("_data") if isinstance(h.get("_data"), dict) else {}
        for k in set(data) | {k for k in h if k != "_data"}:
            v = h.get(k) if h.get(k) not in (None, "") else data.get(k)
            if v not in (None, "", [], {}):
                values[k].append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
print(f"corpus runners={n_runners}  fields={len(values)}  checks={len(checks)}")

rows = []
for c in checks:
    if not c["fields"]:
        c["status"] = "UNRESOLVED"
        rows.append(c); continue
    tot = sum(len(values.get(f, [])) for f in c["fields"])
    hit = sum(sum(c["kw"] in v for v in values.get(f, [])) for f in c["fields"])
    c["nonempty"], c["hits"] = tot, hit
    c["status"] = "FIELD_EMPTY" if tot == 0 else ("DEAD" if hit == 0 else ("RARE" if hit < 10 else "OK"))
    rows.append(c)

json.dump(rows, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for st in ("FIELD_EMPTY", "DEAD", "RARE"):
    print(f"\n===== {st}")
    for c in rows:
        if c["status"] == st:
            print(f"  {c['file']}:{c['line']} {c['func']}  '{c['kw']}' in {c['fields']}  hits={c.get('hits')}/{c.get('nonempty')}")
print(f"\n===== UNRESOLVED ({sum(c['status']=='UNRESOLVED' for c in rows)}) — engine-internal strings / not a Logic field")
for c in rows:
    if c["status"] == "UNRESOLVED":
        print(f"  {c['file']}:{c['line']} {c['func']}  '{c['kw']}' in {c['expr']}")

# vocabulary per field referenced by DEAD/RARE checks
voc_fields = sorted({f for c in rows if c["status"] in ("DEAD", "RARE") for f in c["fields"]})
print("\n===== label vocabulary (digits → #, top 12) for fields with DEAD/RARE checks")
for f in voc_fields:
    shapes = Counter(re.sub(r"[+-]?\d+(?:\.\d+)?", "#", v)[:70] for v in values.get(f, []))
    print(f"--- {f} (non-empty {len(values.get(f, []))})")
    for s, n in shapes.most_common(12):
        print(f"     {n:6d}  {s}")
