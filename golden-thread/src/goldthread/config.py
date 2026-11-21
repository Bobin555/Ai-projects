"""Load and validate packs."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from goldthread.core import (
    JOBS,
    Budget,
    CoverageRule,
    DocumentEntry,
    EvalCase,
    LayoutRecipe,
    LinkType,
    ModelSpec,
    RecordSchema,
    RecordType,
)


class PackError(Exception):
    """A pack is missing a file or fails validation."""


HOSTED_PROVIDERS = {"claude"}
LOCAL_PROVIDERS = {"fake"}
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

REQUIRED_FILES = (
    "pack.yaml", "register.csv", "records.yaml", "aliases.csv",
    "rules.md", "answer_format.md", "outside.md", "tests.csv",
)
REGISTER_HEADER = ["doc_id", "title", "layout", "revision", "date", "status", "supersedes", "url", "sha256"]
TESTS_HEADER = ["id", "question", "expected_sources", "expected_point", "expect_not_found", "status"]


@dataclass(frozen=True)
class Pack:
    name: str
    description: str
    sensitivity: str
    offline: bool
    source_dir: Path | None
    withheld_patterns: tuple[str, ...]
    models: Mapping[str, ModelSpec]
    budget: Budget
    register: tuple[DocumentEntry, ...]
    schema: RecordSchema
    layouts: Mapping[str, LayoutRecipe]
    aliases_path: Path
    rules: str
    answer_format: str
    outside: str
    tests: tuple[EvalCase, ...]
    root: Path
    data_dir: Path


def load_pack(root: Path, data_root: Path | None = None) -> Pack:
    root = Path(root)
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            raise PackError(f"missing pack file: {name}")
    if not (root / "layouts").is_dir():
        raise PackError("missing pack folder: layouts/")

    meta = _load_yaml(root / "pack.yaml")
    for key in ("name", "description", "sensitivity", "offline", "models", "budget"):
        if key not in meta:
            raise PackError(f"pack.yaml: missing key '{key}'")
    name = str(meta["name"])
    if not ID_RE.match(name):
        raise PackError(f"invalid pack name '{name}'")
    sensitivity = str(meta["sensitivity"])
    if sensitivity not in ("public", "sensitive"):
        raise PackError(f"pack.yaml: sensitivity must be public or sensitive, not '{sensitivity}'")
    offline = meta["offline"]
    if not isinstance(offline, bool):
        raise PackError("pack.yaml: offline must be true or false")
    if sensitivity == "sensitive" and not offline:
        raise PackError("sensitive pack must be offline")

    models = _parse_models(meta["models"], offline)
    budget = _parse_budget(meta["budget"])
    withheld = tuple(str(p) for p in (meta.get("withheld_patterns") or []))
    for pattern in withheld:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise PackError(f"invalid withheld pattern {pattern!r}: {exc}") from exc
    source_dir = meta.get("source_dir")
    schema = _parse_schema(_load_yaml(root / "records.yaml"))

    if data_root is None:
        data_root = default_data_root(root)

    return Pack(
        name=name,
        description=str(meta["description"]),
        sensitivity=sensitivity,
        offline=offline,
        source_dir=(root / str(source_dir)) if source_dir else None,
        withheld_patterns=withheld,
        models=models,
        budget=budget,
        register=_parse_register(root / "register.csv"),
        schema=schema,
        layouts=_parse_layouts(root / "layouts", schema),
        aliases_path=root / "aliases.csv",
        rules=(root / "rules.md").read_text(encoding="utf-8"),
        answer_format=(root / "answer_format.md").read_text(encoding="utf-8"),
        outside=(root / "outside.md").read_text(encoding="utf-8"),
        tests=_parse_tests(root / "tests.csv"),
        root=root,
        data_dir=Path(data_root) / name,
    )


def default_data_root(pack_root: Path) -> Path:
    """$GT_DATA_DIR if set; else <project>/data for a pack in <project>/packs/<name>; else ./data."""
    if os.environ.get("GT_DATA_DIR"):
        return Path(os.environ["GT_DATA_DIR"])
    pack_dir = Path(pack_root).resolve()
    if pack_dir.parent.name == "packs":
        return pack_dir.parent.parent / "data"
    return Path.cwd() / "data"


def pack_version(pack: Pack) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in pack.root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(pack.root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def update_register_checksum(pack: Pack, doc_id: str, revision: str, sha256: str) -> None:
    path = pack.root / "register.csv"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if i == 0 or not line.strip():
            continue
        row = next(csv.reader([line]))
        if len(row) == len(REGISTER_HEADER) and row[0] == doc_id and row[3] == revision:
            row[-1] = sha256
            out = io.StringIO()
            csv.writer(out, lineterminator="").writerow(row)
            ending = line[len(line.rstrip("\r\n")):]
            lines[i] = out.getvalue() + ending
            path.write_text("".join(lines), encoding="utf-8")
            return
    raise PackError(f"register row not found: {doc_id}@{revision}")


# --- helpers -----------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PackError(f"{path.name}: expected a mapping at the top level")
    return data


def _parse_models(raw: Any, offline: bool) -> dict[str, ModelSpec]:
    if not isinstance(raw, dict):
        raise PackError("pack.yaml: models must be a mapping")
    models: dict[str, ModelSpec] = {}
    for job in JOBS:
        if job not in raw:
            raise PackError(f"pack.yaml: models: missing job '{job}'")
        spec = raw[job]
        try:
            model = ModelSpec(**spec)
        except TypeError as exc:
            raise PackError(f"pack.yaml: models.{job}: {exc}") from exc
        if model.provider not in HOSTED_PROVIDERS | LOCAL_PROVIDERS:
            raise PackError(f"unknown provider '{model.provider}' for job '{job}'")
        if offline and model.provider in HOSTED_PROVIDERS:
            raise PackError(f"offline pack cannot use hosted provider '{model.provider}' for job '{job}'")
        models[job] = model
    return models


def _parse_budget(raw: Any) -> Budget:
    try:
        budget = Budget(float(raw["per_run_usd"]), float(raw["per_month_usd"]))
    except (TypeError, KeyError, ValueError) as exc:
        raise PackError(f"pack.yaml: budget needs per_run_usd and per_month_usd: {exc}") from exc
    if budget.per_run_usd < 0 or budget.per_month_usd < 0:
        raise PackError("pack.yaml: budget limits cannot be negative")
    return budget


def _read_csv(path: Path, header: list[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != header:
            raise PackError(f"{path.name}: header must be {','.join(header)}")
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _parse_register(path: Path) -> tuple[DocumentEntry, ...]:
    entries: list[DocumentEntry] = []
    seen: set[str] = set()
    for row in _read_csv(path, REGISTER_HEADER):
        entry = DocumentEntry(**row)
        if not ID_RE.match(entry.doc_id):
            raise PackError(f"invalid doc_id '{entry.doc_id}'")
        if not ID_RE.match(entry.revision):
            raise PackError(f"invalid revision '{entry.revision}' for {entry.doc_id}")
        if entry.status not in ("issued", "superseded"):
            raise PackError(f"{entry.key}: status must be issued or superseded")
        if entry.key in seen:
            raise PackError(f"duplicate register row {entry.key}")
        seen.add(entry.key)
        entries.append(entry)
    for entry in entries:
        if entry.supersedes and entry.supersedes not in seen:
            raise PackError(f"{entry.key}: supersedes unknown {entry.supersedes}")
    return tuple(entries)


def _parse_schema(raw: dict[str, Any]) -> RecordSchema:
    types: dict[str, RecordType] = {}
    for name, spec in (raw.get("record_types") or {}).items():
        fields = tuple(spec.get("fields") or ())
        required = tuple(spec.get("required") or ())
        missing = [f for f in required if f not in fields]
        if missing:
            raise PackError(f"records.yaml: {name}: required fields not in fields: {missing}")
        identity = tuple(spec.get("identity") or ())
        unknown = [f for f in identity if f not in fields]
        if unknown:
            raise PackError(f"records.yaml: {name}: identity fields not in fields: {unknown}")
        types[name] = RecordType(name, str(spec["prefix"]), fields, required, identity)

    links: dict[str, LinkType] = {}
    for name, spec in (raw.get("link_types") or {}).items():
        from_type, field_name = spec.get("from"), spec.get("field")
        targets = dict(spec.get("to") or {})
        for t in [from_type, *targets]:
            if t not in types:
                raise PackError(f"records.yaml: link '{name}': unknown record type '{t}'")
        if field_name not in types[from_type].fields:
            raise PackError(f"records.yaml: link '{name}': {from_type} has no field '{field_name}'")
        for t, target_field in targets.items():
            if target_field not in types[t].fields:
                raise PackError(f"records.yaml: link '{name}': {t} has no field '{target_field}'")
        scope = spec.get("scope")
        if scope not in ("chunk", "code"):
            raise PackError(f"records.yaml: link '{name}': scope must be chunk or code")
        links[name] = LinkType(name, from_type, field_name, targets, scope, bool(spec.get("reverse", False)))

    coverage: list[CoverageRule] = []
    for spec in raw.get("coverage") or []:
        rule = CoverageRule(**spec)
        if rule.type not in types:
            raise PackError(f"records.yaml: coverage '{rule.name}': unknown record type '{rule.type}'")
        used = [x for x in (rule.missing_incoming, rule.has_incoming, rule.has_outgoing) if x]
        if len(used) != 1 or used[0] not in links:
            raise PackError(f"records.yaml: coverage '{rule.name}': needs exactly one known link type")
        coverage.append(rule)
    return RecordSchema(types, links, tuple(coverage))


def _parse_layouts(folder: Path, schema: RecordSchema) -> dict[str, LayoutRecipe]:
    layouts: dict[str, LayoutRecipe] = {}
    for path in sorted(folder.glob("*.yaml")):
        raw = _load_yaml(path)
        recipe = LayoutRecipe(
            layout=str(raw.get("layout", "")),
            looks_for=tuple(raw.get("looks_for") or ()),
            instructions=str(raw.get("instructions", "")),
            example=str(raw.get("example", "")),
        )
        if recipe.layout != path.stem:
            raise PackError(f"layouts/{path.name}: layout must be '{path.stem}'")
        for t in recipe.looks_for:
            if t not in schema.record_types:
                raise PackError(f"layouts/{path.name}: unknown record type '{t}'")
        layouts[recipe.layout] = recipe
    return layouts


def _parse_tests(path: Path) -> tuple[EvalCase, ...]:
    cases: list[EvalCase] = []
    for row in _read_csv(path, TESTS_HEADER):
        if row["expect_not_found"] not in ("yes", "no"):
            raise PackError(f"tests.csv: {row['id']}: expect_not_found must be yes or no")
        if row["status"] not in ("draft", "approved"):
            raise PackError(f"tests.csv: {row['id']}: status must be draft or approved")
        sources = tuple(s.strip() for s in row["expected_sources"].split(";") if s.strip())
        cases.append(EvalCase(row["id"], row["question"], sources, row["expected_point"],
                              row["expect_not_found"] == "yes", row["status"]))
    return tuple(cases)
