"""Enumerate the meaning atoms of an experimental intent, each with an `ablate` function.

An atom is the smallest piece of recruiter meaning the schema can carry separately: one skill, one proficiency value, one location entry, one
degree stream, one work mode, one semantic exclusion, one sourcing path (and each thing inside it). `ablate(d)` returns a deep copy of the intent
dict with exactly that atom removed (or, for a qualifier, reset). The compiler's output delta under ablation is the atom's destination.

KIND: MEANING (recruiter meaning), RECORD (a reconciliation decision), METADATA (provenance, archetype, labels)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent

Dict_ = Dict[str, Any]


@dataclass
class Atom:
    id: str
    concept: str
    scope: str                     # "global" | "path:<id>"
    kind: str                      # MEANING | RECORD | METADATA
    label: str                     # short semantic value
    ablate: Callable[[Dict_], Dict_] = field(repr=False, default=lambda d: d)
    strength: Optional[str] = None
    proficiency: Optional[str] = None
    relationship: Optional[str] = None

    def row(self) -> Dict[str, Any]:
        return {"id": self.id, "concept": self.concept, "scope": self.scope, "kind": self.kind, "value": self.label,
                "strength": self.strength, "proficiency": self.proficiency, "relationship": self.relationship}


def _short(s: Any, n: int = 70) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _mut(fn: Callable[[Dict_], None]) -> Callable[[Dict_], Dict_]:
    def run(d: Dict_) -> Dict_:
        c = copy.deepcopy(d)
        fn(c)
        return c
    return run


def _pop(key: str, i: int):
    return _mut(lambda c: c[key].pop(i))


def _set(key: str, value: Any):
    return _mut(lambda c: c.__setitem__(key, value))


def _loc_atoms(loc: Optional[Dict_], scope: str, getter: Callable[[Dict_], Optional[Dict_]], setter_prefix: str) -> List[Atom]:
    """Atoms of a location record (global or inside a path). `getter(c)` returns the (mutable) location dict inside a copied intent."""
    if not loc:
        return []
    out: List[Atom] = []
    st = loc.get("strength")

    def mk(concept, label, fn, idx=""):
        out.append(Atom(f"{scope}|{concept}{idx}", concept, scope, "MEANING", label, _mut(fn), strength=st))

    for j, e in enumerate(loc.get("entries") or []):
        mk("location.entry", e, lambda c, j=j: getter(c)["entries"].pop(j), f"[{j}]")
    for j, e in enumerate(loc.get("countries") or []):
        mk("location.country", e, lambda c, j=j: getter(c)["countries"].pop(j), f"[{j}]")
    if loc.get("radius"):
        r = loc["radius"]
        mk("location.radius", f"{r['value']} {r['unit']} around {r['around']}", lambda c: getter(c).__setitem__("radius", None))
    if loc.get("remote"):
        mk("location.remote", loc["remote"], lambda c: getter(c).__setitem__("remote", None))
    if loc.get("work_mode"):
        mk("location.work_mode", loc["work_mode"], lambda c: getter(c).__setitem__("work_mode", None))
    return out


def _sen_atoms(sen: Optional[Dict_], scope: str, getter: Callable[[Dict_], Optional[Dict_]], with_value: bool) -> List[Atom]:
    if not sen:
        return []
    out: List[Atom] = []
    st = sen.get("strength")
    if with_value:
        out.append(Atom(f"{scope}|seniority", "seniority.value", scope, "MEANING", sen["value"], _mut(lambda c: c.__setitem__("seniority", None)), strength=st))
    else:  # path-level seniority: remove the whole override
        out.append(Atom(f"{scope}|seniority", "seniority.value", scope, "MEANING", sen["value"], _mut(lambda c: None), strength=st))
    for j, m in enumerate(sen.get("leadership") or []):
        out.append(Atom(f"{scope}|seniority.leadership[{j}]", "seniority.leadership", scope, "MEANING", m,
                        _mut(lambda c, j=j: getter(c)["leadership"].pop(j)), strength=st))
    for j, m in enumerate(sen.get("alternatives") or []):
        out.append(Atom(f"{scope}|seniority.alternatives[{j}]", "seniority.alternatives", scope, "MEANING", m,
                        _mut(lambda c, j=j: getter(c)["alternatives"].pop(j)), strength=st))
    return out


def enumerate_atoms(intent: ExperimentalHiringIntent) -> List[Atom]:
    d = intent.model_dump()
    A: List[Atom] = []

    # metadata
    arche = d["role_archetype"]["value"]
    other = next(v for v in ("title_defined", "skill_defined", "hybrid") if v != arche)
    A.append(Atom("global|role_archetype", "role_archetype", "global", "METADATA", arche,
                  _mut(lambda c: c["role_archetype"].__setitem__("value", other))))

    def null_all_basis(c):
        def rec(x):
            if isinstance(x, dict):
                for k in list(x.keys()):
                    if k == "basis":
                        x[k] = None
                    else:
                        rec(x[k])
            elif isinstance(x, list):
                for v in x:
                    rec(v)
        rec(c)
    A.append(Atom("global|provenance.basis", "provenance.basis", "global", "METADATA", "per-atom source + verbatim quote (all atoms)", _mut(null_all_basis)))

    # role family
    for i, t in enumerate(d["role_family"]):
        if len(d["role_family"]) > 1:
            A.append(Atom(f"global|role_family[{i}]", "role_family", "global", "MEANING", t, _pop("role_family", i), strength="required"))
        else:
            A.append(Atom(f"global|role_family[{i}]", "role_family", "global", "MEANING", t, _mut(lambda c, i=i: c["role_family"].__setitem__(i, "ZZ ablated title")), strength="required"))

    A += _sen_atoms(d.get("seniority"), "global", lambda c: c["seniority"], True)

    for i, s in enumerate(d["skills"]):
        A.append(Atom(f"global|skill[{i}]", "skill", "global", "MEANING", s["name"], _pop("skills", i),
                      strength=s["strength"], proficiency=s.get("proficiency"), relationship=s["relationship"]))
        if s.get("proficiency"):
            A.append(Atom(f"global|skill.proficiency[{i}]", "skill.proficiency", "global", "MEANING", f"{s['name']} = {s['proficiency']}",
                          _mut(lambda c, i=i: c["skills"][i].__setitem__("proficiency", None)), strength=s["strength"], proficiency=s["proficiency"]))
    for i, g in enumerate(d["skill_any_of"]):
        A.append(Atom(f"global|skill_any_of[{i}]", "skill_any_of", "global", "MEANING", " | ".join(g["any_of"]), _pop("skill_any_of", i),
                      strength=g["strength"], relationship=g["relationship"]))
    for i, c_ in enumerate(d["companies"]):
        A.append(Atom(f"global|company[{i}]", "company", "global", "MEANING", c_["name"], _pop("companies", i),
                      strength=c_["strength"], relationship=c_["relationship"]))
    if d.get("company_scale"):
        cs = d["company_scale"]
        A.append(Atom("global|company_scale", "company_scale", "global", "MEANING", f">={cs['minimum_employees']} employees", _set("company_scale", None),
                      strength=cs["strength"], relationship=cs["relationship"]))
    if d.get("education"):
        ed = d["education"]
        for j, x in enumerate(ed["degrees"]):
            A.append(Atom(f"global|education.degree[{j}]", "education.degree", "global", "MEANING", x, _mut(lambda c, j=j: c["education"]["degrees"].pop(j)), strength=ed["strength"]))
        for j, x in enumerate(ed["streams"]):
            A.append(Atom(f"global|education.stream[{j}]", "education.stream", "global", "MEANING", x, _mut(lambda c, j=j: c["education"]["streams"].pop(j)), strength=ed["strength"]))
    if d.get("experience"):
        ex = d["experience"]
        if ex.get("minimum_years") is not None:
            A.append(Atom("global|experience.min", "experience.min", "global", "MEANING", f"{ex['minimum_years']}+ years", _mut(lambda c: c["experience"].__setitem__("minimum_years", None)), strength=ex["strength"]))
        if ex.get("maximum_years") is not None:
            A.append(Atom("global|experience.max", "experience.max", "global", "MEANING", f"<= {ex['maximum_years']} years", _mut(lambda c: c["experience"].__setitem__("maximum_years", None)), strength=ex["strength"]))
    A += _loc_atoms(d.get("location"), "global", lambda c: c["location"], "location")
    for i, x in enumerate(d["exclusions"]):
        A.append(Atom(f"global|exclusion[{i}]", f"exclusion.{x['kind']}", "global", "MEANING", x["value"], _pop("exclusions", i), strength="required"))
    for i, x in enumerate(d["semantic_exclusions"]):
        A.append(Atom(f"global|semantic_exclusion[{i}]", "semantic_exclusion", "global", "MEANING", _short(x["concept"]), _pop("semantic_exclusions", i), strength="required"))
    for i, x in enumerate(d["domain"]):
        A.append(Atom(f"global|domain[{i}]", "domain", "global", "MEANING", _short(x["name"]), _pop("domain", i), strength=x["strength"]))
    for i, x in enumerate(d["evidence_signals"]):
        A.append(Atom(f"global|evidence[{i}]", "evidence_signal", "global", "MEANING", _short(x["name"]), _pop("evidence_signals", i), strength=x["strength"]))
    for i, x in enumerate(d["reconciliations"]):
        A.append(Atom(f"global|reconciliation[{i}]", "reconciliation", "global", "RECORD", f"{x['action']}: {_short(x['topic'], 60)}", _pop("reconciliations", i)))

    # sourcing paths and everything inside them
    for pi, p in enumerate(d["sourcing_paths"]):
        sc = f"path:{p['id']}"
        A.append(Atom(f"{sc}|path", "sourcing_path", sc, "MEANING", f"{p['id']} ({p['strategy']}): {_short(p['label'], 40)}", _pop("sourcing_paths", pi)))
        A += _sen_atoms(p.get("seniority"), sc, lambda c, pi=pi: c["sourcing_paths"][pi]["seniority"], False)
        # path-level seniority "value" ablation = drop the override
        for a in A:
            if a.scope == sc and a.concept == "seniority.value":
                a.ablate = _mut(lambda c, pi=pi: c["sourcing_paths"][pi].__setitem__("seniority", None))
        if p.get("experience"):
            ex = p["experience"]
            if ex.get("minimum_years") is not None:
                A.append(Atom(f"{sc}|experience.min", "experience.min", sc, "MEANING", f"{ex['minimum_years']}+ years", _mut(lambda c, pi=pi: c["sourcing_paths"][pi]["experience"].__setitem__("minimum_years", None)), strength=ex["strength"]))
            if ex.get("maximum_years") is not None:
                A.append(Atom(f"{sc}|experience.max", "experience.max", sc, "MEANING", f"<= {ex['maximum_years']} years", _mut(lambda c, pi=pi: c["sourcing_paths"][pi]["experience"].__setitem__("maximum_years", None)), strength=ex["strength"]))
        A += _loc_atoms(p.get("location"), sc, lambda c, pi=pi: c["sourcing_paths"][pi]["location"], "location")
        for i, s in enumerate(p["skills"]):
            A.append(Atom(f"{sc}|skill[{i}]", "skill", sc, "MEANING", s["name"], _mut(lambda c, pi=pi, i=i: c["sourcing_paths"][pi]["skills"].pop(i)),
                          strength=s["strength"], proficiency=s.get("proficiency"), relationship=s["relationship"]))
            if s.get("proficiency"):
                A.append(Atom(f"{sc}|skill.proficiency[{i}]", "skill.proficiency", sc, "MEANING", f"{s['name']} = {s['proficiency']}",
                              _mut(lambda c, pi=pi, i=i: c["sourcing_paths"][pi]["skills"][i].__setitem__("proficiency", None)), strength=s["strength"], proficiency=s["proficiency"]))
        for i, x in enumerate(p["domain"]):
            A.append(Atom(f"{sc}|domain[{i}]", "domain", sc, "MEANING", _short(x["name"]), _mut(lambda c, pi=pi, i=i: c["sourcing_paths"][pi]["domain"].pop(i)), strength=x["strength"]))
    return A
