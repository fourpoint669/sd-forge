"""Model code runs only in a separate `python -I` worker that a timeout kills (with anything it started);
the loop detector evaluates model expressions in-process only through a strict allowlist."""
import ast
import json
import os
import shutil
import signal
import sys
import time

import numpy as np
import pytest

import loop_detector as ld
import generated_code_check
import validate
from conftest import BASS, mdl_text


@pytest.fixture(scope="module")
def bass_py(tmp_path_factory):
    d = tmp_path_factory.mktemp("safety")
    p = d / "bass.mdl"
    p.write_text(mdl_text(BASS, final_time=30, time_step=0.0625))
    return validate.translate(str(p), str(d))


def _inject(bass_py, tmp_path, body):
    """Copy the model and replace the q component's `return 0.38` with `body` (4-space indented lines)."""
    py = tmp_path / "evil.py"
    shutil.copy(bass_py, py)
    src = py.read_text()
    assert src.count("    return 0.38\n") == 1
    py.write_text(src.replace("    return 0.38\n", "".join(f"    {line}\n" for line in body)))
    return str(py)


def _alive(pid):
    if sys.platform == "win32":        # os.kill(pid, 0) terminates the process there, so ask the OS instead
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)         # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259                                          # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _force_kill(pid):
    if sys.platform == "win32":
        os.system(f"taskkill /F /T /PID {pid} >NUL 2>&1")
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _wait_gone(pid, seconds=2.0):
    end = time.time() + seconds
    while time.time() < end:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


def test_infinite_loop_model_is_killed(bass_py, tmp_path, monkeypatch):
    pidfile = tmp_path / "pid"
    py = _inject(bass_py, tmp_path, ["import os", f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))",
                                     "while True:", "    pass"])
    monkeypatch.setattr(validate, "TIMEOUT_BASE_S", 8)
    t0 = time.time()
    out = validate.run_batch(py, [{}], workers=1, timeout_per_run=1)
    assert out == [None]
    assert any("timeout after" in str(e) for e in validate.run_batch.last_errors)
    assert time.time() - t0 < 30
    assert _wait_gone(int(pidfile.read_text()))


def test_timeout_kills_grandchildren(bass_py, tmp_path, monkeypatch):
    pidfile = tmp_path / "grandchild"
    py = _inject(bass_py, tmp_path, [
        "import subprocess, sys",
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])",
        f"open({str(pidfile)!r}, 'w').write(str(g.pid))",
        "while True:", "    pass"])
    monkeypatch.setattr(validate, "TIMEOUT_BASE_S", 8)
    assert validate.run_batch(py, [{}], workers=1, timeout_per_run=1) == [None]
    pid = int(pidfile.read_text())
    try:
        assert _wait_gone(pid), "grandchild process survived the worker timeout"
    finally:
        _force_kill(pid)


def test_worker_is_isolated(bass_py, tmp_path, monkeypatch):
    """Characterization: the worker runs with -I, so PYTHONPATH and the script directory are ignored."""
    info = tmp_path / "info.json"
    py = _inject(bass_py, tmp_path, ["import json, sys",
                                     f"open({str(info)!r}, 'w').write(json.dumps({{'isolated': sys.flags.isolated, 'path': sys.path}}))",
                                     "return 0.38"])
    monkeypatch.setenv("PYTHONPATH", "/sdforge-marker")
    assert validate.run_batch(py, [{}], workers=1)[0] is not None
    got = json.loads(info.read_text())
    assert got["isolated"] == 1
    assert not any("sdforge-marker" in p for p in got["path"])


# ---------------------------------------------------------------- loop-detector expression sandbox
def _compile(src):
    return ld.compile_expr(ast.parse(src, mode="eval").body, {"x"})


# User-requested addition (deviation from the plan): the exact exploit, with x() and with the literal bare x.
# Both must be rejected by the keyword-argument rule, not by the bare-name rule.
@pytest.mark.parametrize("src", [
    "np.abs(x(), where=np.load('/tmp/payload.npy', allow_pickle=True))",
    "np.abs(x, where=np.load(..., allow_pickle=True))",
])
def test_np_load_keyword_exploit_rejected_by_keyword_rule(src):
    with pytest.raises(ld.Unsupported) as e:
        _compile(src)
    assert "keyword" in str(e.value) and "bare name" not in str(e.value), str(e.value)


@pytest.mark.parametrize("src", [
    "x().__class__",
    "np.linalg.inv(x())",
    "np.abs(x(), **x())",
    "np.abs(*x())",
])
def test_compile_expr_rejects_attribute_escape(src):
    with pytest.raises(ld.Unsupported):
        _compile(src)


def test_compiled_expressions_have_no_builtins():
    f = _compile("np.minimum(x(), 2)")
    assert f.__globals__["__builtins__"] == {}
    assert np.array_equal(f({"x": np.array([1.0, 3.0])}), np.array([1.0, 2.0]))


def test_timeout_cleanup_is_bounded_when_a_descendant_escapes_the_group(bass_py, tmp_path, monkeypatch):
    """Inspection IR-001: a descendant in its own session survives the group kill and keeps the worker's
    pipes open; cleanup must still return (the escaped process itself is outside the kill's reach)."""
    import threading
    pidfile = tmp_path / "escaped"
    py = _inject(bass_py, tmp_path, [
        "import subprocess, sys",
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'], start_new_session=True)",
        f"open({str(pidfile)!r}, 'w').write(str(g.pid))",
        "while True:", "    pass"])
    monkeypatch.setattr(validate, "TIMEOUT_BASE_S", 8)
    result = {}
    th = threading.Thread(target=lambda: result.setdefault("out", validate.run_batch(py, [{}], workers=1, timeout_per_run=1)),
                          daemon=True)
    th.start()
    th.join(45)
    try:
        assert not th.is_alive(), "timeout cleanup hung on a descendant holding the worker's pipes"
        assert result["out"] == [None]
        assert any("timeout after" in str(e) for e in validate.run_batch.last_errors)
    finally:
        try:
            _force_kill(int(pidfile.read_text()))
        except (FileNotFoundError, ValueError):
            pass
        th.join(10)


# ---- a crafted comment must not become code in the generated model file ----------------------------------------------
# PySD writes each Vensim comment into a triple-quoted docstring without escaping it, so a comment that closes the
# docstring adds code to the translation. translate() refuses such a file before any worker imports it. These models are
# only translated, never run, and the payloads are inert.

_MDL = '''{UTF-8}
Stock= INTEG (
	inflow,
		10)
	~	Firm
	~	COMMENT
	|

inflow= 
	"my var" * 0.1
	~	Firm/Month
	~	x
	|

"my var"= 5
	~	Dmnl
	~	x
	|

FINAL TIME  = 10
	~	Month
	~	x
	|

INITIAL TIME  = 0
	~	Month
	~	x
	|

SAVEPER  = 
        TIME STEP
	~	Month
	~	x
	|

TIME STEP  = 1
	~	Month
	~	x
	|
'''


def _translate_with_comment(tmp_path, comment):
    p = tmp_path / "crafted.mdl"
    p.write_text(_MDL.replace("COMMENT", comment))
    (tmp_path / "out").mkdir()
    return validate.translate(str(p), str(tmp_path / "out"))


def test_a_plain_comment_still_translates(tmp_path):
    py = _translate_with_comment(tmp_path, "a harmless note with 'quotes' and a hash # sign")
    assert generated_code_check.problems(py) == []


@pytest.mark.parametrize("comment", [
    'x""" + str(open("never_written","w").write("x")) + """y',          # expression built around the docstring
    'x""" + __import__("os").getcwd() + """y',                          # import by name
    'x""" + str(().__class__.__bases__) + """y',                        # attribute walk to builtins
])
def test_a_comment_that_breaks_out_of_its_docstring_is_refused(tmp_path, comment):
    with pytest.raises(RuntimeError, match="translation refused"):
        _translate_with_comment(tmp_path, comment)
    assert not (tmp_path / "never_written").exists()


def test_the_shipped_models_pass_the_screen(bass_py):
    assert generated_code_check.problems(bass_py) == []
