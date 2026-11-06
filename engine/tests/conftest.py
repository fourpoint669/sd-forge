"""Shared helpers: build tiny Vensim .mdl fixtures inline and translate them with PySD (in a worker)."""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import validate  # noqa: E402


def pytest_configure(config):
    # The suite exercises the repository's own projects: pin the projects root (engine/sd_paths.py) so the results do not
    # depend on the folder pytest is started from. Tests of other roots pass an explicit root or environment.
    os.environ["SD_PROJECTS_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "projects")


def pytest_addoption(parser):
    parser.addoption("--require-browser", action="store_true", default=False,
                     help="fail (not skip) browser tests when node + Playwright + Chromium are missing; "
                          "same as SD_REQUIRE_BROWSER=1. Use it for release runs.")


def mdl_text(equations, final_time=10, time_step=0.125, time_unit="Month"):
    """equations: list of (definition, units), e.g. ("Stock = INTEG(inflow, 1)", "Thing")."""
    body = "{UTF-8}\n"
    for eq, units in equations:
        body += f"{eq}\n\t~\t{units}\n\t~\t\t|\n\n"
    body += ("********************************************************\n\t.Control\n"
             "********************************************************~\n\t\tSimulation Control Parameters\n\t|\n\n"
             f"FINAL TIME  = {final_time}\n\t~\t{time_unit}\n\t~\t\t|\n\n"
             f"INITIAL TIME  = 0\n\t~\t{time_unit}\n\t~\t\t|\n\n"
             f"SAVEPER  = TIME STEP\n\t~\t{time_unit} [0,?]\n\t~\t\t|\n\n"
             f"TIME STEP  = {time_step}\n\t~\t{time_unit} [0,?]\n\t~\t\t|\n")
    return body


@pytest.fixture
def build(tmp_path):
    """build(name, equations, **control) -> path of the PySD-translated .py."""
    def _build(name, equations, **kw):
        d = tmp_path / name
        d.mkdir()
        p = d / f"{name}.mdl"
        p.write_text(mdl_text(equations, **kw))
        return validate.translate(str(p), str(d))
    return _build


EXPONENTIAL = [("Stock = INTEG(growth, 1)", "Widget"), ("growth = rate * Stock", "Widget/Month"),
               ("rate = 0.1", "1/Month")]

LOGISTIC = [("Population = INTEG(net growth, initial population)", "Person"), ("initial population = 10", "Person"),
            ("net growth = fractional growth * Population", "Person/Month"),
            ("fractional growth = max growth rate * (1 - Population / carrying capacity)", "1/Month"),
            ("max growth rate = 0.5", "1/Month"), ("carrying capacity = 1000", "Person")]

BASS = [("Potential Adopters = INTEG(-adoption, total population)", "Person"),
        ("Adopters = INTEG(adoption, 0)", "Person"),
        ("adoption = adoption from advertising + adoption from word of mouth", "Person/Month"),
        ("adoption from advertising = p * Potential Adopters", "Person/Month"),
        ("adoption from word of mouth = q * Potential Adopters * adopter fraction", "Person/Month"),
        ("adopter fraction = Adopters / total population", "Dmnl"),
        ("p = 0.03", "1/Month"), ("q = 0.38", "1/Month"), ("total population = 1000", "Person")]

NO_LOOP = [("Tank = INTEG(fill, 0)", "Litre"), ("fill = fill rate", "Litre/Month"), ("fill rate = 2", "Litre/Month")]


SPEC = textwrap.dedent("""
    dominance_min_period = 1.0
    [model]
    name = "bass-fixture"
    mdl = "bass.mdl"
    py = "bass.py"
    time_unit = "Month"
    final_time = 30
    time_step = 0.0625
    saveper = 1
    key_outputs = ["Adopters", "adoption"]

    [parameters.p]
    base = 0.03
    low = 0.01
    high = 0.05
    domain = [0, 1]
    role = "rate"
    [parameters.q]
    base = 0.38
    low = 0.3
    high = 0.5
    distribution = "triangular"
    domain = [0, 5]
    role = "rate"
    [parameters."total population"]
    base = 1000
    low = 500
    high = 2000
    distribution = "loguniform"
    domain = [1, 1e6]

    [[conservation]]
    name = "population"
    stocks = ["Potential Adopters", "Adopters"]

    [[extreme]]
    name = "no advertising and no adopters: nobody adopts"
    set = { p = 0 }
    expect = [{ var = "Adopters", stat = "max", op = "<=", value = 1e-9 }]

    [reference]
    function = "bass"
    compare = ["Adopters"]
    nrmse_max = 0.10
    args = { p = { param = "p" }, q = { param = "q" }, N = { param = "total population" } }
    peak = { var = "adoption", tolerance = 0.25 }
    modes = [{ var = "Adopters", mode = "s-curve" }, { var = "adoption", mode = "peak" }]

    [sectors]
    market = ["Potential Adopters", "Adopters", "total population", "adopter fraction"]
    adoption = ["adoption", "adoption from advertising", "adoption from word of mouth", "p", "q"]

    [[loops]]
    name = "R word of mouth"
    polarity = "R"
    variables = ["Adopters", "adopter fraction", "adoption from word of mouth", "adoption"]
    [[loops]]
    name = "B saturation (word of mouth)"
    polarity = "B"
    variables = ["Potential Adopters", "adoption from word of mouth", "adoption"]
    [[loops]]
    name = "B saturation (advertising)"
    polarity = "B"
    variables = ["Potential Adopters", "adoption from advertising", "adoption"]

    [montecarlo]
    n = 1000
    seed = 7
    metrics = [{ name = "adopters_m10", var = "Adopters", stat = "value_at", time = 10 },
               { name = "peak_month", var = "adoption", stat = "time_of_max" }]

    [policy]
    objective = "adopters_m10"
    [[policies]]
    name = "base"
    [[policies]]
    name = "more advertising"
    changes = { p = { mul = 2 } }
""")


def make_project(d, equations, spec_text, **control):
    """Write <d>/bass.mdl from equations, translate it, write validation.toml; returns d."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "bass.mdl").write_text(mdl_text(equations, **control))
    validate.translate(str(d / "bass.mdl"), str(d))
    (d / "validation.toml").write_text(spec_text)
    return d


@pytest.fixture
def bass_project(tmp_path):
    return make_project(tmp_path / "proj", BASS, SPEC, final_time=30, time_step=0.0625)


# Single-flow Bass: adoption = (p + q F) * Potential. Loops by hand: B (Potential -> adoption -> Potential),
# R (Adopters -> adopter fraction -> adoption -> Adopters).
BASS_SINGLE = [("Potential Adopters = INTEG(-adoption, total population)", "Person"),
               ("Adopters = INTEG(adoption, 0)", "Person"),
               ("adoption = (p + q * adopter fraction) * Potential Adopters", "Person/Month"),
               ("adopter fraction = Adopters / total population", "Dmnl"),
               ("p = 0.03", "1/Month"), ("q = 0.38", "1/Month"), ("total population = 1000", "Person")]

SIR = [("Susceptible = INTEG(-infection, initial susceptible)", "Person"), ("initial susceptible = 990", "Person"),
       ("Infected = INTEG(infection - recovery, initial infected)", "Person"), ("initial infected = 10", "Person"),
       ("Recovered = INTEG(recovery, 0)", "Person"),
       ("infection = contact rate * Susceptible * Infected / total population", "Person/Day"),
       ("recovery = Infected / illness duration", "Person/Day"),
       ("contact rate = 0.5", "1/Day"), ("illness duration = 5", "Day"), ("total population = 1000", "Person")]

# Two stocks and a causal link between them, but no cycle (Source is never drained).
CHAIN = [("Source = INTEG(feed, 1)", "Item"), ("feed = feed rate", "Item/Month"), ("feed rate = 2", "Item/Month"),
         ("Sink = INTEG(transfer, 0)", "Item"), ("transfer = k * Source", "Item/Month"), ("k = 0.1", "1/Month")]

# Three stocks, each fed by the other two: two distinct 6-vertex cycles on the SAME vertex set
# (A -> B -> C -> A and A -> C -> B -> A) plus three 4-vertex pair loops.
RING3 = [("A = INTEG(flow A, 1)", "Thing"), ("flow A = kA * (B + C)", "Thing/Month"), ("kA = 0.01", "1/Month"),
         ("B = INTEG(flow B, 1)", "Thing"), ("flow B = kB * (A + C)", "Thing/Month"), ("kB = 0.01", "1/Month"),
         ("C = INTEG(flow C, 1)", "Thing"), ("flow C = kC * (A + B)", "Thing/Month"), ("kC = 0.01", "1/Month")]
