"""Runner da suíte QA + cálculo de cobertura de linhas executáveis via stdlib `trace`."""

import ast
import sys
import threading
import trace
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC_DIR = ROOT / "src" / "modules"


def _executable_lines(py_file: Path) -> set[int]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and not (
            isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str)
        ):
            lines.add(node.lineno)
    return lines


def _run_all():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(ROOT / "tests"), pattern="test_*.py")
    return unittest.TextTestRunner(verbosity=2).run(suite)


def main() -> int:
    tracer = trace.Trace(count=1, trace=0)
    threading.settrace(tracer.globaltrace)
    try:
        result = tracer.runfunc(_run_all)
    finally:
        threading.settrace(None)

    results = tracer.results()
    total_exec = 0
    total_hit = 0
    print("\n=== Cobertura por Módulo (src/modules) ===")
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if py_file.name == "__init__.py" or "ingestion" in py_file.parts:
            continue
        resolved = str(py_file.resolve())
        exec_lines = _executable_lines(py_file)
        hit_lines = {ln for (fn, ln), cnt in results.counts.items() if cnt > 0 and Path(fn).resolve() == Path(resolved) and ln in exec_lines}
        pct = (len(hit_lines) / len(exec_lines) * 100.0) if exec_lines else 100.0
        total_exec += len(exec_lines)
        total_hit += len(hit_lines)
        rel = py_file.relative_to(ROOT).as_posix()
        print(f"  {rel:58s} {len(hit_lines):4d}/{len(exec_lines):4d} ({pct:5.1f}%)")

    overall = (total_hit / total_exec * 100.0) if total_exec else 100.0
    print(f"TOTAL COBERTURA (runtime modules): {total_hit}/{total_exec} ({overall:.1f}%)")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
