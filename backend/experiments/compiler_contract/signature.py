"""Compiler-output signatures, diffs, and a read-set tracer. Pure functions over the UNCHANGED compiler."""

from __future__ import annotations

import json
from typing import Any, Dict, FrozenSet, Iterable, List, Set, Tuple

from pydantic import BaseModel

from backend.services.compiler_audit import judge_checklist
from backend.services.search_compiler import CompiledPlan, canonicalize, compile_intent


def leaves(tree: Any, acc: List[Tuple[str, str, str]] | None = None) -> List[Tuple[str, str, str]]:
    acc = [] if acc is None else acc
    if isinstance(tree, dict) and "op" in tree:
        for c in tree["conditions"]:
            leaves(c, acc)
    elif isinstance(tree, dict):
        acc.append((tree.get("field"), tree.get("type"), json.dumps(tree.get("value"), ensure_ascii=False)))
    return acc


def audit_rows(plan: CompiledPlan) -> List[Tuple]:
    return [(c.source, c.strength, c.route, tuple(c.provider_fields), c.temporal, c.capability, c.note) for c in plan.audit]


def signature(plan: CompiledPlan) -> Dict[str, Any]:
    return {
        "leaves": frozenset(leaves(plan.filter_tree)),
        "tree": repr(canonicalize(plan.filter_tree)),
        "audit": frozenset(audit_rows(plan)),
        "titles": tuple(plan.retrieval_title_family),
        "warnings": tuple(plan.warnings),
        "normalizations": tuple(json.dumps(n, sort_keys=True, ensure_ascii=False) for n in plan.normalizations),
        "checklist": tuple(judge_checklist(plan)),
    }


def delta(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    """What `base` has that `other` lacks (the atom's destination when `other` is the ablated compile), plus what `other` gains."""
    d: Dict[str, Any] = {
        "leaves_lost": sorted(base["leaves"] - other["leaves"]),
        "leaves_gained": sorted(other["leaves"] - base["leaves"]),
        "audit_lost": sorted(base["audit"] - other["audit"], key=repr),
        "audit_gained": sorted(other["audit"] - base["audit"], key=repr),
        "titles_changed": base["titles"] != other["titles"],
        "warnings_changed": base["warnings"] != other["warnings"],
        "normalizations_changed": base["normalizations"] != other["normalizations"],
        "checklist_lost": sorted(set(base["checklist"]) - set(other["checklist"])),
        "checklist_gained": sorted(set(other["checklist"]) - set(base["checklist"])),
        "tree_changed": base["tree"] != other["tree"],
    }
    d["empty"] = not any(v for v in d.values())
    return d


def compile_dict(d: Dict[str, Any], model_cls) -> CompiledPlan:
    return compile_intent(model_cls.model_validate(d))


# --- read-set tracer ----------------------------------------------------------------------------------------------------


class _Traced:
    """Transparent proxy that records every attribute path `compile_intent` reads. Lists become plain lists of proxies; scalars are returned raw."""

    def __init__(self, obj: BaseModel, path: str, sink: Set[str]):
        object.__setattr__(self, "_o", obj)
        object.__setattr__(self, "_p", path)
        object.__setattr__(self, "_s", sink)

    def __getattr__(self, name: str):
        o = object.__getattribute__(self, "_o")
        p = object.__getattribute__(self, "_p")
        s = object.__getattribute__(self, "_s")
        v = getattr(o, name)
        path = f"{p}.{name}" if p else name
        s.add(path)
        return _wrap(v, path, s)

    def __bool__(self) -> bool:
        return True


def _wrap(v: Any, path: str, sink: Set[str]) -> Any:
    if isinstance(v, BaseModel):
        return _Traced(v, path + ("[]" if path.endswith("]") else ""), sink)
    if isinstance(v, (list, tuple)):
        return [_wrap(x, path + "[]", sink) for x in v]
    return v


def read_set(intent: BaseModel) -> Set[str]:
    sink: Set[str] = set()
    compile_intent(_Traced(intent, "", sink))  # type: ignore[arg-type]
    return {p.replace("[][]", "[]") for p in sink}


def schema_paths(model_cls, prefix: str = "") -> Set[str]:
    """Every field path of a model, with `[]` for list members. Used to compare against the read set."""
    import typing

    out: Set[str] = set()
    for name, info in model_cls.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        out.add(path)
        ann = info.annotation
        for _ in range(3):
            args = typing.get_args(ann)
            if typing.get_origin(ann) in (list, List, typing.Union, getattr(__import__("types"), "UnionType", None)) and args:
                ann = next((a for a in args if a is not type(None)), ann)
                inner_is_list = typing.get_origin(info.annotation) in (list, List)
            else:
                break
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            multi = typing.get_origin(info.annotation) in (list, List)
            out |= schema_paths(ann, path + ("[]" if multi else ""))
    return out
