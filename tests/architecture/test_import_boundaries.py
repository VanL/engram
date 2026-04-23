from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[2] / "engram"


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    source: str
    target: str

    def render(self) -> str:
        return f"{self.path.relative_to(PACKAGE_ROOT.parent)}:{self.line} {self.source} -> {self.target}"


class ImportVisitor(ast.NodeVisitor):
    def __init__(self, *, path: Path, module: str) -> None:
        self.path = path
        self.module = module
        self.violations: list[Violation] = []
        self._type_checking_depth = 0

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_test(node.test):
            self._type_checking_depth += 1
            for child in node.body:
                self.visit(child)
            self._type_checking_depth -= 1
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self._type_checking_depth:
            return
        for alias in node.names:
            self._check_target(node.lineno, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._type_checking_depth:
            return
        if node.module is None:
            return
        target = _absolute_import_target(self.module, node.module, node.level)
        self._check_target(node.lineno, target)
        for alias in node.names:
            self._check_root_import(node.lineno, target, alias.name)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in {"_store", "_index"} and self.module != "engram.core.memory":
            self.violations.append(
                Violation(
                    path=self.path,
                    line=node.lineno,
                    source=self.module,
                    target=f"private attribute {node.attr}",
                )
            )
        self.generic_visit(node)

    def _check_target(self, line: int, target: str) -> None:
        if self.module.startswith("engram.cli") and target == "engram":
            self.violations.append(
                Violation(
                    path=self.path,
                    line=line,
                    source=self.module,
                    target=target,
                )
            )
        for banned in _banned_imports_for(self.module):
            if target == banned or target.startswith(f"{banned}."):
                self.violations.append(
                    Violation(
                        path=self.path,
                        line=line,
                        source=self.module,
                        target=target,
                    )
                )

    def _check_root_import(self, line: int, target: str, imported_name: str) -> None:
        if self.module.startswith("engram.dogfood.") and target == "engram":
            if imported_name == "Engram":
                self.violations.append(
                    Violation(
                        path=self.path,
                        line=line,
                        source=self.module,
                        target="engram.Engram",
                    )
                )


def test_import_boundaries() -> None:
    violations: list[Violation] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = ImportVisitor(path=path, module=module)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    assert not violations, "\n".join(violation.render() for violation in violations)


def test_store_code_uses_explicit_select_columns() -> None:
    offenders: list[str] = []
    for path in sorted((PACKAGE_ROOT / "store").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "SELECT *" in text.upper():
            offenders.append(str(path.relative_to(PACKAGE_ROOT.parent)))

    assert not offenders, "\n".join(offenders)


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
    return ".".join(relative.parts)


def _absolute_import_target(current_module: str, module: str, level: int) -> str:
    if level == 0:
        return module
    parts = current_module.split(".")[:-level]
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def _is_type_checking_test(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or (
        isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"
    )


def _banned_imports_for(module: str) -> tuple[str, ...]:
    if module.startswith("engram.core."):
        return (
            "engram.background",
            "engram.commands",
            "engram.client",
            "engram.cli",
            "engram.dogfood",
        )
    if module == "engram.store.core":
        return ("engram.store._sql.sqlite",)
    if module.startswith("engram.index."):
        return (
            "engram.commands",
            "engram.core",
            "engram.client",
            "engram.cli",
            "engram.background",
            "engram.dogfood",
        )
    if module.startswith("engram.store."):
        return (
            "engram.commands",
            "engram.client",
            "engram.cli",
            "engram.background",
            "engram.dogfood",
        )
    if module.startswith("engram.runtime."):
        return (
            "engram.background",
            "engram.commands",
            "engram.client",
            "engram.cli",
            "engram.core",
            "engram.dogfood",
            "engram.index",
            "engram.store",
        )
    if module.startswith("engram.commands."):
        return ("engram.cli", "engram.client", "engram.dogfood")
    if module.startswith("engram.cli"):
        return ("engram.core",)
    if module.startswith("engram.client"):
        return ("engram.core",)
    if module.startswith("engram.dogfood."):
        return ("engram.store", "engram.index", "engram.core")
    return ()
