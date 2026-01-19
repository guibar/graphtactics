"""Type stubs for anytree library.

This minimal stub treats all anytree exports as Any to silence type checker
warnings while still allowing the code to work correctly.
"""

from typing import Any

# Core classes
class NodeMixin:
    parent: Any
    children: tuple[Any, ...]
    is_leaf: bool
    is_root: bool
    root: Any
    siblings: tuple[Any, ...]
    leaves: tuple[Any, ...]
    path: tuple[Any, ...]
    ancestors: tuple[Any, ...]
    descendants: tuple[Any, ...]
    depth: int
    height: int

# Iteration
class PreOrderIter:
    def __init__(self, node: Any, filter_: Any = None, stop: Any = None, maxlevel: int | None = None) -> None: ...
    def __iter__(self) -> Any: ...
    def __next__(self) -> Any: ...

# Search functions
def findall(
    node: Any,
    filter_: Any = None,
    stop: Any = None,
    maxlevel: int | None = None,
    mincount: int | None = None,
    maxcount: int | None = None,
) -> tuple[Any, ...]: ...
def findall_by_attr(
    node: Any,
    value: Any,
    name: str = "name",
    maxlevel: int | None = None,
    mincount: int | None = None,
    maxcount: int | None = None,
) -> tuple[Any, ...]: ...
def find(node: Any, filter_: Any = None, stop: Any = None, maxlevel: int | None = None) -> Any: ...
def find_by_attr(node: Any, value: Any, name: str = "name", maxlevel: int | None = None) -> Any: ...

# Allow any other attribute access
def __getattr__(name: str) -> Any: ...
