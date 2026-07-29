#!/usr/bin/env python3
"""Reference architecture scanner for Python/FastAPI Clean Architecture projects.

Slim, generic, stdlib-only. Detects six categories of structural drift:

  LAYER-IMPORT-DOMAIN   domain/ depending on infrastructure/, api/, or application/
  LAYER-IMPORT-API      api/ reaching past application/ into infrastructure/
  DB-IN-APPLICATION     application/ importing Session/select/SQLModel session APIs
  INLINE-IMPORT         function-body import (circular-dependency smell)
  GOD-FILE              file longer than --max-file-lines (default 600)
  GOD-CLASS             class with more than --max-class-methods methods (default 25)

Defaults assume greenfield-style layout: app/services/<svc>/{domain,application,
infrastructure,api}. Override via --service-glob and --root for other layouts.
Skip a category with --disable=DB-IN-APPLICATION,GOD-FILE etc.

Designed to be wired into devt's /devt:arch-health workflow via .devt/config.json:

  "arch_scanner": {
    "command": "python3 .devt/rules/arch-scan.py --json",
    "report_dir": "docs/reports"
  }

Stdout is the report; stderr is human-readable progress. With --json, stdout is
a single JSON document the architect agent parses into findings.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — override via CLI
# ---------------------------------------------------------------------------

# Standard Clean Architecture layer names, ordered by dependency direction
# (domain has zero dependencies; api/presentation depends on all inner layers).
LAYERS = ("domain", "application", "infrastructure", "api")

# DB / ORM symbols that indicate direct database access. Application layer must
# go through repository interfaces, not these primitives.
DB_SYMBOLS = frozenset(
    {
        "Session",
        "AsyncSession",
        "select",
        "Select",
        "create_engine",
        "sessionmaker",
        "scoped_session",
    }
)

DB_MODULES = frozenset(
    {
        "sqlalchemy",
        "sqlalchemy.orm",
        "sqlalchemy.future",
        "sqlmodel",
        "sqlmodel.ext",
    }
)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    category: str
    severity: str  # "critical" | "high" | "medium" | "low"
    file: str
    line: int
    message: str
    detail: str = ""


@dataclass
class Report:
    scanner: str = "devt-python-arch-scan"
    version: str = "1.0"
    scanned_files: int = 0
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer detection
# ---------------------------------------------------------------------------


def detect_layer(rel_path: Path) -> str | None:
    """Return the layer name if `rel_path` lives in one, else None.

    Walks parts looking for a directory named after one of LAYERS. The first
    match wins, so `app/services/photos/api/v1/routes.py` → "api".
    """
    for part in rel_path.parts:
        if part in LAYERS:
            return part
    return None


def detect_service(rel_path: Path, service_root_parts: tuple[str, ...]) -> str | None:
    """Return the service name (module under service_root) if any.

    For `app/services/photos/api/routes.py` with service_root `app/services`,
    returns "photos".
    """
    parts = rel_path.parts
    rl = len(service_root_parts)
    if len(parts) <= rl:
        return None
    if parts[:rl] != service_root_parts:
        return None
    return parts[rl]


# ---------------------------------------------------------------------------
# AST visitors
# ---------------------------------------------------------------------------


class ScanVisitor(ast.NodeVisitor):
    """Single-pass AST visitor that collects raw signals for one file.

    Signals are emitted as Finding objects via callbacks so the orchestrator
    decides which categories are enabled. Keeping signal collection separate
    from category logic makes --disable trivial.
    """

    def __init__(self, file_path: Path, source_lines: int):
        self.file_path = file_path
        self.source_lines = source_lines
        self.imports: list[tuple[int, str]] = []  # (lineno, module_name)
        self.imported_names: list[tuple[int, str, str]] = []  # (lineno, module, name)
        self.inline_imports: list[tuple[int, str]] = []
        self.classes: list[tuple[int, str, int]] = []  # (lineno, name, method_count)
        self._function_depth = 0

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod = alias.name
            if self._function_depth > 0:
                self.inline_imports.append((node.lineno, mod))
            self.imports.append((node.lineno, mod))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Relative imports (level > 0) are intra-package; we record the resolved
        # module as the literal so callers can normalize if needed.
        mod = node.module or ""
        if self._function_depth > 0:
            self.inline_imports.append((node.lineno, mod))
        self.imports.append((node.lineno, mod))
        for alias in node.names:
            self.imported_names.append((node.lineno, mod, alias.name))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        method_count = sum(
            1 for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        self.classes.append((node.lineno, node.name, method_count))
        # Recurse into all children including methods. Method bodies ARE
        # function scope, so visit_FunctionDef will correctly bump
        # _function_depth and detect inline imports inside methods.
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Categorical detectors (stateless — operate on visitor output + file context)
# ---------------------------------------------------------------------------


def detect_layer_violations(
    rel_path: Path,
    layer: str,
    visitor: ScanVisitor,
) -> Iterable[Finding]:
    """Domain may not depend on application/infrastructure/api.
    API may not reach past application into infrastructure.
    """
    if layer == "domain":
        for lineno, mod in visitor.imports:
            for forbidden in ("application", "infrastructure", "api"):
                # Match as a path segment, not a substring, to avoid flagging
                # a legitimate import like `myapp.api_keys`.
                if any(p == forbidden for p in mod.split(".")):
                    yield Finding(
                        category="LAYER-IMPORT-DOMAIN",
                        severity="critical",
                        file=str(rel_path),
                        line=lineno,
                        message=f"domain layer imports from '{forbidden}' layer",
                        detail=f"import target: {mod}. Domain must depend on nothing.",
                    )
                    break  # one finding per import, not per forbidden token
    elif layer == "api":
        for lineno, mod in visitor.imports:
            if any(p == "infrastructure" for p in mod.split(".")):
                # Allow same-package infrastructure imports? No — api should go
                # through application. Flag all.
                yield Finding(
                    category="LAYER-IMPORT-API",
                    severity="high",
                    file=str(rel_path),
                    line=lineno,
                    message="api layer imports directly from infrastructure",
                    detail=f"import target: {mod}. Route handlers should call services, not repositories.",
                )


def detect_db_in_application(
    rel_path: Path,
    layer: str,
    visitor: ScanVisitor,
) -> Iterable[Finding]:
    """Application layer must use repository interfaces, not raw DB primitives."""
    if layer != "application":
        return
    for lineno, mod, name in visitor.imported_names:
        if mod in DB_MODULES and name in DB_SYMBOLS:
            yield Finding(
                category="DB-IN-APPLICATION",
                severity="high",
                file=str(rel_path),
                line=lineno,
                message=f"application imports '{name}' from '{mod}'",
                detail="Application services should depend on repository interfaces, not Session/select/engine primitives. Move data access to infrastructure/repositories.py.",
            )


def detect_inline_imports(
    rel_path: Path,
    visitor: ScanVisitor,
) -> Iterable[Finding]:
    for lineno, mod in visitor.inline_imports:
        yield Finding(
            category="INLINE-IMPORT",
            severity="medium",
            file=str(rel_path),
            line=lineno,
            message=f"inline import inside function body: '{mod}'",
            detail="Inline imports usually mask circular dependencies. Move to module top, or refactor to break the cycle.",
        )


def detect_god_file(
    rel_path: Path,
    visitor: ScanVisitor,
    max_lines: int,
) -> Iterable[Finding]:
    if visitor.source_lines > max_lines:
        yield Finding(
            category="GOD-FILE",
            severity="medium",
            file=str(rel_path),
            line=1,
            message=f"file is {visitor.source_lines} lines (limit {max_lines})",
            detail="Long files usually mix unrelated responsibilities. Consider extracting cohesive subsets to sibling modules.",
        )


def detect_god_class(
    rel_path: Path,
    visitor: ScanVisitor,
    max_methods: int,
) -> Iterable[Finding]:
    for lineno, name, method_count in visitor.classes:
        if method_count > max_methods:
            yield Finding(
                category="GOD-CLASS",
                severity="medium",
                file=str(rel_path),
                line=lineno,
                message=f"class '{name}' has {method_count} methods (limit {max_methods})",
                detail="Single-Responsibility Principle: split methods into cohesive collaborator classes.",
            )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def iter_python_files(root: Path) -> Iterable[Path]:
    # Skip non-source trees plus `.devt/` itself — when this scanner is
    # deployed at .devt/rules/arch-scan.py via /devt:init, scanning .devt
    # would have it audit itself plus playbook examples masquerading as
    # Python files. .devt is plugin scaffolding, not project source.
    skip_dirs = {".venv", "venv", ".tox", "__pycache__", ".git", "node_modules", "build", "dist", ".devt"}
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        yield path


def scan_file(
    project_root: Path,
    file_path: Path,
    service_root_parts: tuple[str, ...],
    enabled: set[str],
    max_file_lines: int,
    max_class_methods: int,
) -> tuple[ScanVisitor | None, list[Finding]]:
    rel = file_path.relative_to(project_root)
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [
            Finding(
                category="SCAN-ERROR",
                severity="low",
                file=str(rel),
                line=0,
                message=f"could not read file: {exc}",
            )
        ]

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return None, [
            Finding(
                category="SCAN-ERROR",
                severity="low",
                file=str(rel),
                line=exc.lineno or 0,
                message=f"syntax error during parse: {exc.msg}",
            )
        ]

    visitor = ScanVisitor(file_path=file_path, source_lines=source.count("\n") + 1)
    visitor.visit(tree)

    layer = detect_layer(rel)
    findings: list[Finding] = []

    if layer and ("LAYER-IMPORT-DOMAIN" in enabled or "LAYER-IMPORT-API" in enabled):
        findings.extend(detect_layer_violations(rel, layer, visitor))
    if layer and "DB-IN-APPLICATION" in enabled:
        findings.extend(detect_db_in_application(rel, layer, visitor))
    if "INLINE-IMPORT" in enabled:
        findings.extend(detect_inline_imports(rel, visitor))
    if "GOD-FILE" in enabled:
        findings.extend(detect_god_file(rel, visitor, max_file_lines))
    if "GOD-CLASS" in enabled:
        findings.extend(detect_god_class(rel, visitor, max_class_methods))

    return visitor, findings


def emit_text(report: Report, stream) -> None:
    if not report.findings:
        print(f"OK — scanned {report.scanned_files} files, no findings.", file=stream)
        return
    by_severity: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_severity.setdefault(f.severity, []).append(f)
    print(f"Architecture scan — {report.scanned_files} files scanned, {len(report.findings)} findings", file=stream)
    print("", file=stream)
    for sev in ("critical", "high", "medium", "low"):
        items = by_severity.get(sev, [])
        if not items:
            continue
        print(f"[{sev.upper()}] {len(items)} finding(s)", file=stream)
        for f in items:
            print(f"  {f.file}:{f.line} [{f.category}] {f.message}", file=stream)
            if f.detail:
                print(f"    -> {f.detail}", file=stream)
        print("", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generic Python/FastAPI Clean-Architecture scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", default=".", help="Project root (default: cwd)")
    parser.add_argument(
        "--service-root",
        default="app/services",
        help="Slash-separated path under root where services live (default: app/services). Set to empty string to scan all .py files without service grouping.",
    )
    parser.add_argument(
        "--max-file-lines",
        type=int,
        default=600,
        help="GOD-FILE threshold (default: 600)",
    )
    parser.add_argument(
        "--max-class-methods",
        type=int,
        default=25,
        help="GOD-CLASS threshold (default: 25)",
    )
    parser.add_argument(
        "--disable",
        default="",
        help="Comma-separated category names to skip (e.g. GOD-FILE,GOD-CLASS)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report to stdout (text summary to stderr)",
    )
    parser.add_argument(
        "--fail-on",
        default="critical,high",
        help="Severities that cause non-zero exit (default: critical,high). Empty disables.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.root).resolve()
    if not project_root.is_dir():
        print(f"error: --root not a directory: {project_root}", file=sys.stderr)
        return 2

    all_categories = {
        "LAYER-IMPORT-DOMAIN",
        "LAYER-IMPORT-API",
        "DB-IN-APPLICATION",
        "INLINE-IMPORT",
        "GOD-FILE",
        "GOD-CLASS",
    }
    disabled = {c.strip().upper() for c in args.disable.split(",") if c.strip()}
    enabled = all_categories - disabled

    service_root_parts = tuple(p for p in args.service_root.strip("/").split("/") if p)

    report = Report()
    for file_path in iter_python_files(project_root):
        report.scanned_files += 1
        _, findings = scan_file(
            project_root=project_root,
            file_path=file_path,
            service_root_parts=service_root_parts,
            enabled=enabled,
            max_file_lines=args.max_file_lines,
            max_class_methods=args.max_class_methods,
        )
        report.findings.extend(findings)

    if args.json:
        json.dump({**asdict(report), "findings": [asdict(f) for f in report.findings]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        emit_text(report, sys.stderr)
    else:
        emit_text(report, sys.stdout)

    fail_severities = {s.strip() for s in args.fail_on.split(",") if s.strip()}
    if any(f.severity in fail_severities for f in report.findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
