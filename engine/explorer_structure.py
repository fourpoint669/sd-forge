"""Diagram data for the sd-explorer Structure tab: nodes, pipes, causal links, delay marks, loops and a layout.

Usage:  python -I engine/explorer_structure.py [--projects-root DIR] projects/<model>|<model>     (prints a summary)

Everything is read from validated files or computed from the committed model:
  nodes   every model variable (controls excluded) with kind (stock, flow, auxiliary, parameter, constant), sector
          (validation.toml [sectors]), exogenous = parameter or constant, level 0 (stocks, flows) or 1 (the rest; the
          page shows level 1 when zoomed in or in 'show all variables')
  pipes   one per flow: from the stock(s) it drains (or a cloud source), to the stock(s) it fills (or a cloud sink),
          read from the stocks' INTEG equations
  links   one per dependency in an equation (the edges engine/loop_detector.py uses); kind 'pipe' for flow -> stock,
          'info' otherwise. sign = '+' or '-' from the LTM link scores of a PySD base run (dt saving), as T8 reads them;
          a link that is zero throughout the base run takes its sign from the run with [loop_check] overrides when the
          spec has one; otherwise '?'
  delay   on every link from a stock listed as a first-order delay in delay_audit.json into its outflow chain, with
          the audit's order, time constant, form and type
  loops   the validated loops in loop_dominance.json (cycle order, declared names and polarity)
  layout  deterministic: one region per sector; sectors holding stocks first, in the order material flows between them,
          then the others in [sectors] order; inside a region the stocks run upstream to downstream with their valves on
          the pipe row, auxiliaries below, exogenous inputs at the bottom. Two layouts: 'detail' (every variable) and
          'overview' (stocks and flows on one unwrapped pipe row under a title band and an empty corridor that carries
          routed pipes). Nodes keep region-local coordinates (lx, ly / olx, oly) so the page can re-pack the regions to
          its canvas; x, y / ox, oy are a default landscape packing.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sd_paths  # noqa: E402
import delay_audit  # noqa: E402  (one reader for a stock's flow terms)
import explorer_meta  # noqa: E402
import export_js  # noqa: E402
import loop_detector as ld  # noqa: E402  (read-only dependency)
import validate  # noqa: E402  (read-only dependency)

CELL_W, ROW_H, PAD, TITLE_H, GAP = 150, 104, 28, 40, 72
PER_ROW = 6          # nodes per row inside a detail region
ASPECT = 1.6         # target width / height of the default packing (the page re-packs regions to its canvas)
# overview regions: a title band, then an empty corridor that carries routed pipes between regions, then the single
# pipe row; below it room for stock names at their largest zoomed-out size (2 lines of 40-unit text)
OV_TITLE_BAND = 64
OV_CORRIDOR = 56
OV_TOP = OV_TITLE_BAND + OV_CORRIDOR        # 120: the top of the tallest mark on the pipe row
OV_ROW_Y = OV_TOP + 32                       # pipe row centre (tank half-height 28 + 4)
OV_BOTTOM = OV_ROW_Y + 30 + 2 * 46 + 16      # stock name below the tank, two lines at 40 units, then padding


def _signs(model, spec, base):
    """{(x, z): (sign, method)}. Method 'ltm': LTM link scores of a base run (dt saving), as T8 reads them;
    'loop_check': the same in the [loop_check] run, for links that are zero throughout the base run;
    'perturbation': for links an LTM score cannot sign (e.g. from a constant, which never changes during a run), the
    sign of z(x + h) - z(x) with h = 1e-6 x max(|x|, 1), evaluated on the base run at every saved step;
    'perturbation_optional_on': the same on a run with every parameter whose base is 0 set to its validated high (all
    inside [low, high]), for links whose effect is switched off at base; 'inactive': still no effect (a switch threshold,
    a non-binding floor): sign '0', drawn dotted grey and explained in the page legend."""
    runs = [{"params": base, "saveper_dt": True}]
    loop_set = (spec.get("loop_check") or {}).get("set", {})
    if loop_set:
        runs.append({"params": dict(base, **loop_set), "saveper_dt": True})
    dfs = validate.run_batch(spec["model"]["py_path"], runs)
    if len(dfs) != len(runs) or any(df is None for df in dfs):
        raise RuntimeError(f"sign runs: PySD returned {len(dfs)} results for {len(runs)} runs (or a run failed)")
    out = {}
    for df, method in zip(dfs, ("ltm", "loop_check")):
        ls = ld.link_scores(model, ld.values_from_frame(model, df))
        for e, arr in ls.items():
            lab = ld._sign_label(arr)
            if out.get(e, ("?",))[0] == "?":
                out[e] = (lab, method) if lab in ("+", "-", "+/-") else ("?", None)
    names = set(model.comps)
    optional_on = dict(base, **{k: p["high"] for k, p in spec["parameters"].items()
                                if p["base"] == 0 and p["high"] > 0 and p.get("distribution") != "fixed"})
    on_df = validate.run_batch(spec["model"]["py_path"], [{"params": optional_on, "saveper_dt": True}])[0]
    for df, method in ((dfs[0], "perturbation"), (on_df, "perturbation_optional_on")):
        v = ld.values_from_frame(model, df)
        for x, z in ld.graph(model).edges():
            if out.get((x, z), ("?",))[0] != "?":
                continue
            c = model.comps[z]
            f = ld.compile_expr(c.flow if c.ctype == "Stateful" else c.expr, names)
            hv = dict(v)
            hv[x] = v[x] + 1e-6 * max(float(np.max(np.abs(v[x]))), 1.0)
            d = np.broadcast_to(f(hv), v["time"].shape) - np.broadcast_to(f(v), v["time"].shape)
            lab = ld._sign_label(np.asarray(d, dtype=float))
            if lab != "?":
                out[(x, z)] = (lab, method)
    for e in ld.graph(model).edges():
        if out.get(e, ("?",))[0] == "?":
            out[e] = ("0", "inactive")
    return out


def build_structure(project_dir):
    spec = validate.load_spec(os.path.join(project_dir, "validation.toml"))
    py = spec["model"]["py_path"]
    ir = export_js.load_ir(py)
    meta = explorer_meta.build_metadata(spec, ir, project_dir)["variables"]
    model = ld.parse_model(py)
    names = ir["names"]                                   # py -> real
    by_real = {v: k for k, v in names.items()}
    stocks = sorted(s["py"] for s in ir["stocks"])
    sector_of = {}
    for sec, members in spec.get("sectors", {}).items():
        for v in members:
            if v in by_real:
                sector_of.setdefault(by_real[v], sec)
    sectors = list(spec.get("sectors", {}))
    if any(p not in sector_of for p in names):
        sectors.append("other")

    nodes = {}
    for p in sorted(names):
        kind = meta[names[p]]["kind"]
        nodes[p] = {"id": p, "name": names[p], "kind": kind, "sector": sector_of.get(p, "other"),
                    "exogenous": kind in ("parameter", "constant"), "level": 0 if kind in ("stock", "flow") else 1,
                    "unit": meta[names[p]]["unit"]}

    # pipes from the INTEG equations
    src, dst = {}, {}
    never = delay_audit.never_a_flow(model.comps)   # one definition of what cannot be a valve, shared with the audit
    for s in stocks:
        for sign, f in delay_audit.signed_terms(model.comps[s].flow, 1, never):
            if f not in names:               # belt and braces: a rate that is no diagram node would raise on nodes[f]
                continue
            (src if sign < 0 else dst).setdefault(f, []).append(s)
    flows = sorted(set(src) | set(dst))
    # One flow can drain two stocks (a coflow: a sale leaves the vehicle inventory and the prospect pool). Keeping
    # only the first source hid the other stock's drain, so both ends are lists.
    pipes = [{"flow": f, "from": sorted(src.get(f, [])), "to": sorted(dst.get(f, []))} for f in flows]

    # links and signs
    signs = _signs(model, spec, validate.base_params(spec))
    edges = sorted(ld.graph(model).edges())
    flow_set = set(flows)
    links = []
    audit = json.load(open(os.path.join(project_dir, "delay_audit.json")))
    delays = {by_real[r["stock"]]: r for r in audit["stocks"] if r["first_order_candidate"]}
    for x, z in edges:
        k = {"from": x, "to": z, "kind": "pipe" if (x in flow_set and z in stocks) else "info",
             "sign": signs.get((x, z), ("?", None))[0], "sign_method": signs.get((x, z), ("?", None))[1], "delay": None}
        if x in delays:
            outs = {by_real[o] for o in delays[x]["outflows"]}
            chain = set(outs)
            todo = list(outs)
            while todo:                                   # the outflows and the auxiliaries feeding them
                n = todo.pop()
                for a, b in edges:
                    if b == n and a not in chain and a not in stocks and nodes[a]["kind"] == "auxiliary":
                        chain.add(a)
                        todo.append(a)
            if z in chain or (delays[x]["form"] == "goal_seeking" and z in {f for f in flows if x in dst.get(f, [])}):
                r = delays[x]
                k["delay"] = {"stock": r["stock"], "order": r["order"], "tau": r["tau"], "tau_base": r["tau_base"],
                              "tau_run": r["tau_run"], "tau_var": r["tau_var"], "form": r["form"],
                              "type": r["delay_type"]}
        links.append(k)

    # validated loops
    dom = json.load(open(os.path.join(project_dir, "loop_dominance.json")))
    loops = []
    for lp in dom["loops"]:
        cyc = lp["py"]
        loops.append({"id": lp["id"], "name": lp["name"], "polarity": lp["polarity"], "nodes": cyc,
                      "edges": [[cyc[i], cyc[(i + 1) % len(cyc)]] for i in range(len(cyc))]})

    # a valve sits in the region of its source stock (else its first target) when its declared sector holds neither;
    # the declared sector is kept for the page's information card
    for n in nodes.values():
        n["declared_sector"] = n["sector"]
    for p in pipes:
        ends = p["from"] + p["to"]
        if ends and nodes[p["flow"]]["sector"] not in {nodes[e]["sector"] for e in ends}:
            nodes[p["flow"]]["sector"] = nodes[ends[0]]["sector"]
    regions = _layout(nodes, sectors, pipes, stocks, "detail")
    overview = _layout(nodes, sectors, pipes, stocks, "overview")
    for lp in loops:
        xs = [nodes[n]["x"] for n in lp["nodes"]]
        ys = [nodes[n]["y"] for n in lp["nodes"]]
        lp["x"], lp["y"] = float(np.mean(xs)), float(np.mean(ys))
    for lp in loops:
        pts = [(nodes[n]["ox"], nodes[n]["oy"]) for n in lp["nodes"] if "ox" in nodes[n]]
        if pts:
            lp["ox"], lp["oy"] = float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts]))
    # Pooling panel inputs: conserved stock groups ([[conservation]]) and capacity-capped drains (delay audit)
    pooling = {"groups": [{"name": g["name"], "stocks": [by_real[s] for s in g["stocks"]]} for g in spec.get("conservation", [])],
               # A capped drain whose cap or time constant is an expression rather than a named variable (cap_var /
               # tau_var is None in the audit) has no series for the panel to compare, so it is left out of Pooling
               # rather than crashing the build on by_real[None].
               "capped": [{"stock": by_real[r["stock"]], "stock_name": r["stock"], "cap": by_real[r["cap_var"]],
                           "cap_name": r["cap_var"], "tau": by_real[r["tau_var"]], "tau_name": r["tau_var"],
                           "outflow_names": sorted(r["outflows"])}
                          for r in audit["stocks"]
                          if r["form"] == "drain_capped" and r["cap_var"] in by_real and r["tau_var"] in by_real]}
    delay_list = [{"stock": r["stock"], "stock_id": by_real[r["stock"]], "order": r["order"], "tau": r["tau"],
                   "tau_base": r["tau_base"], "tau_run": r["tau_run"], "tau_var": r["tau_var"], "form": r["form"],
                   "type": r["delay_type"]} for r in audit["stocks"] if r["first_order_candidate"]]
    return {"nodes": nodes, "pipes": pipes, "links": links, "loops": loops, "sectors": regions, "overview": overview,
            "pooling": pooling, "delays": delay_list,
            "overview_geometry": {"title_band": OV_TITLE_BAND, "corridor": OV_CORRIDOR, "row_y": OV_ROW_Y, "gap": GAP},
            "time_step": spec["model"]["time_step"], "time_unit": spec["model"]["time_unit"]}


def _sector_order(nodes, sectors, pipes):
    """Sectors holding stocks first, following the material chain (depth-first along pipes between sectors, starting
    from the first such sector in [sectors] order), then every other sector in [sectors] order."""
    with_stocks = [s for s in sectors if any(n["kind"] == "stock" and n["sector"] == s for n in nodes.values())]
    nxt = {}
    for p in pipes:
        for f in p["from"]:
            for t in p["to"]:
                a, b = nodes[f]["sector"], nodes[t]["sector"]
                if a != b:
                    nxt.setdefault(a, set()).add(b)
    order = []

    def visit(sec):
        if sec in order:
            return
        order.append(sec)
        for b in sorted(nxt.get(sec, ()), key=with_stocks.index):
            visit(b)
    for sec in with_stocks:
        visit(sec)
    return order + [s for s in sectors if s not in order]


def _stock_order(sk, feeds, nodes):
    """Upstream first: Kahn's algorithm on the pipes between the sector's stocks, ties by name; cycles broken by name."""
    left = set(sk)
    order = []
    while left:
        ready = sorted((s for s in left if not any(s in feeds.get(a, ()) for a in left if a != s)),
                       key=lambda s: nodes[s]["name"].lower())
        pick = ready[0] if ready else sorted(left, key=lambda s: nodes[s]["name"].lower())[0]
        order.append(pick)
        left.remove(pick)
    return order


def _layout(nodes, sectors, pipes, stocks, mode):
    """mode 'detail': x, y for every node; 'overview': ox, oy for stocks and flows only (the compact zoomed-out view).
    Returns that mode's sector regions [{sector, x, y, w, h, n}] in display order."""
    kx, ky = {"detail": ("x", "y"), "overview": ("ox", "oy")}[mode]
    lkx, lky = {"detail": ("lx", "ly"), "overview": ("olx", "oly")}[mode]
    feeds = {}
    for p in pipes:
        for t in p["to"]:
            for f in p["from"]:
                feeds.setdefault(f, set()).add(t)
    flow_of = {p["flow"]: p for p in pipes}
    regions, local = [], {}
    for sec in _sector_order(nodes, sectors, pipes):
        members = sorted((n for n in nodes.values() if n["sector"] == sec and (mode == "detail" or n["level"] == 0)),
                         key=lambda n: n["name"].lower())
        if not members:
            continue
        order = _stock_order([n["id"] for n in members if n["kind"] == "stock"], feeds, nodes)
        pipe_row, placed = [], set()
        for s in order:
            ins = sorted((f for f, p in flow_of.items() if s in p["to"] and nodes[f]["sector"] == sec and f not in placed
                          and all(nodes[x]["sector"] != sec for x in p["from"])), key=lambda f: nodes[f]["name"].lower())
            pipe_row += ins
            placed |= set(ins)
            pipe_row.append(s)
            outs = sorted((f for f, p in flow_of.items() if s in p["from"] and nodes[f]["sector"] == sec and f not in placed),
                          key=lambda f: nodes[f]["name"].lower())
            pipe_row += outs
            placed |= set(outs)
        pipe_row += [n["id"] for n in members if n["kind"] == "flow" and n["id"] not in placed]
        aux = [n["id"] for n in members if n["kind"] == "auxiliary"]
        exo = [n["id"] for n in members if n["exogenous"]]
        if mode != "detail":
            aux, exo = [], []
        n_all = sum(1 for n in nodes.values() if n["sector"] == sec)
        if mode == "overview":
            width = 2 * PAD + len(pipe_row) * CELL_W         # one pipe row, never wrapped
            for ci, n in enumerate(pipe_row):
                local[n] = (PAD + (ci + 0.5) * CELL_W, OV_ROW_Y)
            regions.append({"sector": sec, "w": float(width), "h": float(OV_BOTTOM), "n": n_all})
            continue
        grid_rows = []
        for r in (pipe_row, aux, exo):
            for i in range(0, len(r), PER_ROW):
                grid_rows.append(r[i:i + PER_ROW])
        per = max(len(r) for r in grid_rows)
        width = 2 * PAD + per * CELL_W
        for ri, r in enumerate(grid_rows):
            off = (width - 2 * PAD - len(r) * CELL_W) / 2
            for ci, n in enumerate(r):
                local[n] = (PAD + off + (ci + 0.5) * CELL_W, TITLE_H + PAD / 2 + ri * ROW_H + ROW_H / 2)
        regions.append({"sector": sec, "w": float(width), "h": float(TITLE_H + PAD + len(grid_rows) * ROW_H), "n": n_all})
    # rows of regions, wrapped at a width that makes the whole diagram about ASPECT times wider than tall
    area = sum((r["w"] + GAP) * (r["h"] + GAP) for r in regions)
    row_w = max(max(r["w"] for r in regions), (area * ASPECT) ** 0.5)
    x = y = row_h = 0.0
    for r in regions:
        if x > 0 and x + r["w"] > row_w:
            x, y, row_h = 0.0, y + row_h + GAP, 0.0
        r["x"], r["y"] = x, y
        x += r["w"] + GAP
        row_h = max(row_h, r["h"])
    pos = {r["sector"]: (r["x"], r["y"]) for r in regions}
    for n in nodes.values():
        if n["id"] in local:
            lx, ly = local[n["id"]]
            ox, oy = pos[n["sector"]]
            n[kx], n[ky] = float(round(ox + lx, 1)), float(round(oy + ly, 1))
            n[lkx], n[lky] = float(round(lx, 1)), float(round(ly, 1))
    return regions


def main(argv):
    argv, _ = sd_paths.extract_flag(argv)
    if len(argv) != 2:
        print(__doc__)
        return 2
    project = sd_paths.resolve_project(argv[1])
    problem = sd_paths.project_problem(project)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    st = build_structure(project)
    kinds = {}
    for n in st["nodes"].values():
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    print(f"nodes {len(st['nodes'])} {kinds}; pipes {len(st['pipes'])}; links {len(st['links'])} "
          f"({sum(1 for k in st['links'] if k['delay'])} with delay marks, "
          f"{sum(1 for k in st['links'] if k['sign'] == '?')} sign '?'); loops {len(st['loops'])}; "
          f"sectors {[r['sector'] for r in st['sectors']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
