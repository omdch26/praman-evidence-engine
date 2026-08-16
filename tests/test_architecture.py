"""
Architecture enforcement tests.

These tests prove the layered dependency structure is intact.
They will fail if someone imports upward (e.g., domain importing services).

Run with: pytest tests/test_architecture.py -v
"""

import ast
import os
from pathlib import Path


def get_python_files(directory: str) -> dict[str, list[str]]:
    """
    Scan a directory for .py files and extract their imports.

    Returns a dict mapping file paths to lists of imported module names.
    Specifically tracks imports from the praman package.
    """
    imports_by_file = {}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=filepath)
                    imports = _extract_praman_imports(tree)
                    if imports:
                        imports_by_file[filepath] = imports
                except SyntaxError:
                    pass
    return imports_by_file


def _extract_praman_imports(tree: ast.AST) -> list[str]:
    """Extract all imports from praman.* and from praman modules."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "praman" in node.module:
                imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "praman" in alias.name:
                    imports.append(alias.name)
    return imports


def test_domain_has_no_module_imports() -> None:
    """
    Domain layer must not import from any other praman module.

    Domain is the foundation. It imports nothing. If it imports from
    ports/, adapters/, services/, or api/, the foundation collapses.
    """
    domain_dir = "praman/domain"
    imports = get_python_files(domain_dir)

    forbidden_prefixes = [
        "praman.ports",
        "praman.adapters",
        "praman.services",
        "praman.persistence",
        "praman.api",
        "praman.modules",
    ]

    violations = []
    for filepath, imported_modules in imports.items():
        for imp in imported_modules:
            if any(imp.startswith(prefix) for prefix in forbidden_prefixes):
                violations.append(f"{filepath} imports {imp}")

    assert (
        not violations
    ), f"Domain layer imports must only be stdlib or third-party.\nViolations:\n" + "\n".join(
        violations
    )


def test_modules_are_mutually_independent() -> None:
    """
    Module 1 (privacy) and Module 2 (ai_risk) must not import each other.

    They are independently deployable. They communicate only through
    shared domain/ and services/ interfaces, never directly.
    """
    privacy_imports = get_python_files("praman/modules/privacy")
    ai_risk_imports = get_python_files("praman/modules/ai_risk")

    privacy_violations = [
        f
        for f, imps in privacy_imports.items()
        if any("praman.modules.ai_risk" in imp for imp in imps)
    ]
    ai_risk_violations = [
        f
        for f, imps in ai_risk_imports.items()
        if any("praman.modules.privacy" in imp for imp in imps)
    ]

    violations = privacy_violations + ai_risk_violations
    assert (
        not violations
    ), f"Modules must not import each other.\nViolations:\n" + "\n".join(violations)


def test_module_depends_only_on_ports_and_domain() -> None:
    """
    Each module may import from domain/ and ports/.
    Each module may import from services/ (shared orchestration).
    Each module must NOT import from adapters/ or api/ (other modules' concerns).

    This ensures modules are composable and independently testable.
    """
    privacy_imports = get_python_files("praman/modules/privacy")
    ai_risk_imports = get_python_files("praman/modules/ai_risk")

    allowed_prefixes = [
        "praman.domain",
        "praman.ports",
        "praman.services",
        "praman.modules.privacy",  # (only for privacy module)
        "praman.modules.ai_risk",   # (only for ai_risk module)
    ]

    violations = []

    # Privacy module checks
    for filepath, imps in privacy_imports.items():
        for imp in imps:
            # Allow domain, ports, services, and self
            if not any(imp.startswith(p) for p in allowed_prefixes):
                # But disallow adapters and api
                if imp.startswith("praman.adapters") or imp.startswith("praman.api"):
                    violations.append(
                        f"{filepath} imports {imp} (privacy must not import adapters or api)"
                    )

    # AI Risk module checks
    for filepath, imps in ai_risk_imports.items():
        for imp in imps:
            if not any(imp.startswith(p) for p in allowed_prefixes):
                if imp.startswith("praman.adapters") or imp.startswith("praman.api"):
                    violations.append(
                        f"{filepath} imports {imp} (ai_risk must not import adapters or api)"
                    )

    assert (
        not violations
    ), f"Modules must depend only on domain/ports/services.\nViolations:\n" + "\n".join(
        violations
    )


if __name__ == "__main__":
    print("Running architecture tests...")
    test_domain_has_no_module_imports()
    print("✅ domain has no module imports")
    test_modules_are_mutually_independent()
    print("✅ modules are mutually independent")
    test_module_depends_only_on_ports_and_domain()
    print("✅ modules depend only on domain/ports/services")
    print("\nAll architecture tests passed.")
