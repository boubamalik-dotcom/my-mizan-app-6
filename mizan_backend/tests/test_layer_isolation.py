"""Mechanically enforces the Mizan Logic layering rules.

Every module in this codebase *documents* its isolation ("STRICT RULE:
no FastAPI, no SQLAlchemy…"), but until now nothing checked it. A
docstring cannot fail a build, so a single convenient import in a
hurry could quietly couple the pure business rules to the web
framework and no one would notice until the layer was no longer
testable in isolation.

These tests parse the source with `ast` rather than importing it, so a
violation is caught even in a module that is never imported by any
other test.

The rules, as stated across the codebase's own docstrings:

* **Layer 3** (business) imports no web framework, no ORM, and nothing
  from Layers 2, 4, or 5. It is pure Python.
* **Layer 5** (storage) imports nothing from Layers 2, 3, or 4.
* **Layer 4** (data access) imports nothing from Layer 2.
* **Layer 2** may import anything; it is the only layer that sees them
  all, which is what lets it translate between them.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Set, Tuple

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"

#: Packages Layer 3 may never touch. `passlib` and `PyJWT` are
#: deliberately absent: they are framework-agnostic cryptography
#: utilities with no web or ORM dependency, the same way
#: `decimal.Decimal` is just arithmetic (see `auth_service.py`).
FORBIDDEN_IN_LAYER_3 = ("fastapi", "sqlalchemy", "pydantic", "starlette", "redis")


def _module_files(layer: str) -> List[Path]:
    """Every non-empty Python module in `layer`."""
    root = SRC / layer
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts and path.read_text().strip()
    ]


def _imported_names(path: Path) -> Iterator[Tuple[str, int]]:
    """Yields `(imported_module, line_number)` for every import in
    `path`, including relative ones resolved to their layer name.

    A relative import is reported by the layer it reaches into, so
    `from ...layer_4_data_access.x import y` inside Layer 3 surfaces as
    `layer_4_data_access` regardless of how many dots it used.
    """
    tree = ast.parse(path.read_text(), filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                # Relative: the module path already names the target
                # layer when it crosses one.
                yield node.module, node.lineno
            elif node.module:
                yield node.module, node.lineno


def _violations(path: Path, forbidden: Tuple[str, ...]) -> List[str]:
    """Every import in `path` whose top-level package is forbidden."""
    found: List[str] = []
    for module, line in _imported_names(path):
        root = module.split(".")[0]
        if root in forbidden:
            found.append(f"{path.relative_to(SRC)}:{line} imports {module!r}")
    return found


class TestLayer3IsPure:
    """Layer 3 is where the money rules, the chat rules, and now the
    access-control policy live. Keeping it free of frameworks is what
    makes those rules testable exhaustively and in milliseconds."""

    @pytest.mark.parametrize(
        "path", _module_files("layer_3_business"), ids=lambda p: p.name
    )
    def test_no_framework_or_orm_imports(self, path: Path) -> None:
        assert not _violations(path, FORBIDDEN_IN_LAYER_3)

    @pytest.mark.parametrize(
        "path", _module_files("layer_3_business"), ids=lambda p: p.name
    )
    def test_no_imports_from_other_layers(self, path: Path) -> None:
        # Layer 3 sits at the bottom of the dependency graph: it is
        # imported by Layers 2 and 4, and imports neither.
        assert not _violations(
            path, ("layer_2_api", "layer_4_data_access", "layer_5_storage")
        )

    def test_the_authz_and_audit_packages_are_actually_covered(self) -> None:
        # Guards the parametrization itself: if the discovery glob ever
        # stopped finding these packages, the tests above would pass
        # vacuously.
        names = {path.name for path in _module_files("layer_3_business")}
        assert {
            "roles.py",
            "authorization_service.py",
            "authz_exceptions.py",
            "audit_service.py",
            "audit_exceptions.py",
        } <= names


def _is_adapter(path: Path) -> bool:
    """Whether `path` is one of the ports-and-adapters bindings under
    `layer_5_storage/implementations/`.

    Those modules exist precisely to join two layers: each implements a
    Layer 4 repository *interface* using Layer 5 ORM models, returning
    Layer 3 domain objects (see
    `implementations/chat_repository_impl.py`'s own docstring). Seeing
    both sides is their entire job, so the rule below exempts them —
    narrowly, and they are still held to knowing nothing about the API
    layer.

    Their placement under `layer_5_storage/` is a scaffolding
    convention rather than an architectural claim; by dependency
    direction they are Layer 4 adapters.
    """
    return "implementations" in path.parts


class TestLayer5KnowsNothingAbove:
    @pytest.mark.parametrize(
        "path",
        [p for p in _module_files("layer_5_storage") if not _is_adapter(p)],
        ids=lambda p: p.name,
    )
    def test_no_imports_from_layers_2_3_or_4(self, path: Path) -> None:
        # Storage proper — models, CRUD, engine configuration — is the
        # bottom of the stack and must stay reusable without dragging
        # any policy in with it.
        assert not _violations(
            path, ("layer_2_api", "layer_3_business", "layer_4_data_access")
        )

    @pytest.mark.parametrize(
        "path",
        [p for p in _module_files("layer_5_storage") if _is_adapter(p)],
        ids=lambda p: p.name,
    )
    def test_even_the_adapters_know_nothing_about_the_api(self, path: Path) -> None:
        # The exemption above buys them Layers 3 and 4, not Layer 2.
        assert not _violations(path, ("layer_2_api", "fastapi", "starlette"))

    def test_the_exemption_stays_narrow(self) -> None:
        # If a model or CRUD module ever moves under `implementations/`
        # to dodge the rule, this catches the widening.
        adapters = {p.name for p in _module_files("layer_5_storage") if _is_adapter(p)}
        assert all(name.endswith("_impl.py") for name in adapters), adapters


class TestLayer4KnowsNothingAboutTheApi:
    @pytest.mark.parametrize(
        "path", _module_files("layer_4_data_access"), ids=lambda p: p.name
    )
    def test_no_imports_from_layer_2(self, path: Path) -> None:
        # Layer 4 may reach *down* into Layer 5 and reuse Layer 3's
        # domain exceptions, but must never know an HTTP API exists.
        assert not _violations(path, ("layer_2_api",))

    @pytest.mark.parametrize(
        "path", _module_files("layer_4_data_access"), ids=lambda p: p.name
    )
    def test_no_web_framework_imports(self, path: Path) -> None:
        assert not _violations(path, ("fastapi", "starlette"))


class TestStorageAndPolicyRolesAgree:
    """Layer 5 cannot import Layer 3's `Role`, so its default role is a
    plain string. This is the test that keeps the two in step."""

    def test_the_storage_default_names_a_real_role(self) -> None:
        from src.layer_3_business.authz.roles import DEFAULT_ROLE, Role
        from src.layer_5_storage.models.user_model import DEFAULT_USER_ROLE

        assert Role.parse(DEFAULT_USER_ROLE) is DEFAULT_ROLE
