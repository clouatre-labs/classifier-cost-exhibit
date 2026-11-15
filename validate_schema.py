"""
Validate schema of experiment analysis.json files.

Checks that every experiments/*/analysis.json contains the required
top-level fields with correct scalar types, ISO date/timestamp formats,
enum values, token totals consistency, a well-formed scores object, and
that the `experiment` field matches the parent directory slug. Certain
fields are nullable (allowed to be null) while others must have values.

Usage:
    uv run python validate_schema.py [--self-test] [FILE ...]

With no FILE arguments, discovers and validates all
experiments/*/analysis.json files under the repository root.

Exits with 0 if all files pass validation, 1 if any validation fails.

Standard library only; no third-party imports.
"""

import datetime
import json
import math
import pathlib
import re
import shutil
import sys
import tempfile

# Top-level fields that are allowed to be null.
NULLABLE_TOP_FIELDS = {"issue", "orchestrator_session"}

# Run-record fields that are allowed to be null.
NULLABLE_RUN_FIELDS = {"bytes", "note"}

# Top-level fields required to be non-null strings.
STRING_TOP_FIELDS = [
    "schema_version",
    "title",
    "date",
    "model",
    "control_condition",
    "treatment_condition",
    "rubric_version",
    "repo_head",
    "experiment_start",
    "experiment_end",
    "analyzed_at",
    "statistical_test",
    "conclusion",
]

# Top-level fields required to be non-null integers (bool is not an int here).
INTEGER_TOP_FIELDS = ["n_per_group"]

# ISO date (YYYY-MM-DD) and ISO 8601 timestamp formats enforced on top fields.
DATE_TOP_FIELDS = ["date"]
TIMESTAMP_TOP_FIELDS = ["experiment_start", "experiment_end", "analyzed_at"]

REQUIRED_TOP_FIELDS = [
    "experiment",
    *STRING_TOP_FIELDS[:2],
    "issue",
    *STRING_TOP_FIELDS[2:],
    *INTEGER_TOP_FIELDS,
    "orchestrator_session",
    "runs",
    "scores",
    "pre_acknowledged_limitations",
]

REQUIRED_RUN_FIELDS = [
    "group",
    "session_id",
    "messages",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "wall_clock_seconds",
    "bytes",
    "note",
]

# Integer run-record fields (bool is not accepted as an integer).
INTEGER_RUN_FIELDS = ["messages", "input_tokens", "output_tokens", "total_tokens"]

# Number run-record fields (int or float).
NUMBER_RUN_FIELDS = ["wall_clock_seconds"]

ALLOWED_GROUPS = {"control", "treatment"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}")


def _reject_constant(name):
    """json.loads parse_constant hook: reject NaN/Infinity tokens."""
    raise ValueError(f"invalid JSON constant {name}")


def _load_json_strict(text):
    return json.loads(text, parse_constant=_reject_constant)


def _is_finite_number(value):
    """True for a non-bool int or float that is finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_timestamp(value):
    """Accept only full ISO 8601 timestamps with a UTC offset."""
    if not TIMESTAMP_RE.match(value):
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return False
    return True


def validate_top_level(data):
    """Check required keys, scalar types, and date/timestamp formats."""
    errors = []
    for field in REQUIRED_TOP_FIELDS:
        if field not in data:
            errors.append(f"missing top-level field {field}")
            continue
        value = data[field]
        if value is None and field not in NULLABLE_TOP_FIELDS:
            errors.append(f"top-level field {field} is null")
    for field in STRING_TOP_FIELDS:
        if data.get(field) is not None and not isinstance(data[field], str):
            errors.append(f"top-level field {field} is not a string")
    for field in INTEGER_TOP_FIELDS:
        if not _is_int(data.get(field)):
            errors.append(f"top-level field {field} is not an integer")
    for field in DATE_TOP_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and not DATE_RE.match(value):
            errors.append(f"top-level field {field} is not an ISO date (YYYY-MM-DD)")
        elif isinstance(value, str):
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                errors.append(f"top-level field {field} is not a valid calendar date")
    for field in ("issue", "orchestrator_session"):
        if data.get(field) is not None and not isinstance(data[field], str):
            errors.append(f"top-level field {field} is not a string or null")
    for field in TIMESTAMP_TOP_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and not _parse_timestamp(value):
            errors.append(f"top-level field {field} is not an ISO 8601 timestamp")
    limitations = data.get("pre_acknowledged_limitations")
    if limitations is not None:
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) for item in limitations
        ):
            errors.append(
                "top-level field pre_acknowledged_limitations is not an array of strings"
            )
    experiment = data.get("experiment")
    if experiment is not None and not isinstance(experiment, str):
        errors.append("top-level field experiment is not a string")
    return errors


def validate_runs(runs):
    """Check run record structure, enum values, and token totals."""
    errors = []
    if not isinstance(runs, dict):
        return [f"runs is not an object: {type(runs).__name__}"]
    for run_id, record in runs.items():
        if not isinstance(record, dict):
            errors.append(f"run {run_id} is not an object")
            continue
        for field in REQUIRED_RUN_FIELDS:
            if field not in record:
                errors.append(f"run {run_id} missing {field}")
            elif record[field] is None and field not in NULLABLE_RUN_FIELDS:
                errors.append(f"run {run_id} has null {field}")
        group = record.get("group")
        if group is not None and not isinstance(group, str):
            errors.append(f"run {run_id} group is not a string")
        elif group is not None and group not in ALLOWED_GROUPS:
            errors.append(
                f"run {run_id} group {group!r} not in {sorted(ALLOWED_GROUPS)}"
            )
        for field in INTEGER_RUN_FIELDS:
            value = record.get(field)
            if field in record and value is not None and not _is_int(value):
                errors.append(f"run {run_id} field {field} is not an integer")
            elif field in record and value is not None and value < 0:
                errors.append(f"run {run_id} field {field} is negative")
        for field in NUMBER_RUN_FIELDS:
            value = record.get(field)
            if field in record and value is not None and not _is_finite_number(value):
                errors.append(f"run {run_id} field {field} is not a finite number")
            elif field in record and value is not None and value < 0:
                errors.append(f"run {run_id} field {field} is negative")
        for field in ("session_id", "note"):
            if field in record and record[field] is not None and not isinstance(record[field], str):
                errors.append(f"run {run_id} field {field} is not a string or null")
        if "bytes" in record and record["bytes"] is not None and not _is_int(record["bytes"]):
            errors.append(f"run {run_id} field bytes is not an integer or null")
        elif "bytes" in record and record["bytes"] is not None and record["bytes"] < 0:
            errors.append(f"run {run_id} field bytes is negative")
        if (
            _is_int(record.get("input_tokens"))
            and _is_int(record.get("output_tokens"))
            and _is_int(record.get("total_tokens"))
            and record["input_tokens"] + record["output_tokens"] != record["total_tokens"]
        ):
            errors.append(f"run {run_id} total_tokens != input_tokens + output_tokens")
    return errors


def validate_scores(scores, runs):
    """Check the scores object shape: dict of run ID to dict."""
    errors = []
    if not isinstance(scores, dict):
        errors.append(f"scores is not an object: {type(scores).__name__}")
        return errors
    known = set(runs) if isinstance(runs, dict) else set()
    for run_id, entry in scores.items():
        if not isinstance(entry, dict):
            errors.append(f"scores[{run_id}] is not an object")
        if run_id not in known:
            errors.append(f"scores key {run_id} does not match any run ID")
    return errors


def validate_record(data, expected_slug=None):
    """Validate a full analysis.json record.

    If expected_slug is given, the `experiment` field must equal it.
    """
    if not isinstance(data, dict):
        return [f"top-level JSON value is not an object: {type(data).__name__}"]
    errors = validate_top_level(data)
    runs = data.get("runs")
    errors.extend(validate_runs(runs))
    errors.extend(validate_scores(data.get("scores"), runs))
    if (
        expected_slug is not None
        and isinstance(data.get("experiment"), str)
        and data["experiment"] != expected_slug
    ):
        errors.append(
            f"experiment {data['experiment']!r} does not match directory slug {expected_slug!r}"
        )
    return errors


def validate_fold_record(data):
    """Validate a per-fold SECOM record under results/{pilot,raw}/."""
    errors = []
    if not isinstance(data, dict):
        return [f"not an object: {type(data).__name__}"]
    for field in ["schema_version", "run_kind", "experiment", "splitter", "fold", "models"]:
        if field not in data:
            errors.append(f"missing required key {field}")
    if "schema_version" in data and data["schema_version"] != "1.0.0":
        errors.append("schema_version is not '1.0.0'")
    if "run_kind" in data and data["run_kind"] not in ("pilot", "sealed"):
        errors.append("run_kind is not in ['pilot', 'sealed']")
    splitter = data.get("splitter")
    if not isinstance(splitter, dict):
        errors.append("splitter is not an object")
    else:
        for field in ["class", "n_splits", "n_repeats", "random_state"]:
            if field not in splitter:
                errors.append(f"missing required key splitter.{field}")
        if "class" in splitter and splitter["class"] != "RepeatedStratifiedKFold":
            errors.append("splitter.class is not 'RepeatedStratifiedKFold'")
        if not isinstance(splitter.get("random_state"), int):
            errors.append("splitter.random_state is not an integer")
    fold = data.get("fold")
    if not isinstance(fold, dict):
        errors.append("fold is not an object")
    else:
        for field in ["repeat", "split", "index"]:
            if not isinstance(fold.get(field), int) or isinstance(fold.get(field), bool):
                errors.append(f"fold.{field} is not an integer")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        errors.append("models is not a non-empty array")
        return errors
    seen = set()
    allowed = {"knn", "decision_tree", "random_forest", "logistic_regression"}
    for entry in models:
        if not isinstance(entry, dict):
            errors.append("model entry is not an object")
            continue
        name = entry.get("model")
        if name not in allowed:
            errors.append(f"model {name!r} is not one of {sorted(allowed)}")
        if name in seen:
            errors.append(f"duplicate model entry {name!r}")
        seen.add(name)
        metrics = entry.get("metrics")
        if not isinstance(metrics, dict):
            errors.append(f"model {name!r} metrics is not an object")
        else:
            for field in ["accuracy", "recall_fail", "precision_fail"]:
                value = metrics.get(field)
                if not _is_finite_number(value) or value < 0:
                    errors.append(f"model {name!r} metrics.{field} is not a non-negative finite number")
            for field in ["fn", "fp"]:
                if not _is_int(metrics.get(field)) or metrics[field] < 0:
                    errors.append(f"model {name!r} metrics.{field} is not a non-negative integer")
        features = entry.get("features")
        if not isinstance(features, dict):
            errors.append(f"model {name!r} features is not an object")
        else:
            for field in ["raw", "after_variance", "after_correlation"]:
                if not _is_int(features.get(field)) or features[field] < 0:
                    errors.append(f"model {name!r} features.{field} is not a non-negative integer")
        y_true = entry.get("y_true")
        y_prob = entry.get("y_prob")
        if not isinstance(y_true, list) or not y_true:
            errors.append(f"model {name!r} y_true is not a non-empty array")
            y_true = None
        elif not all(_is_int(v) and v in (0, 1) for v in y_true):
            errors.append(f"model {name!r} y_true values are not all 0 or 1")
        if not isinstance(y_prob, list):
            errors.append(f"model {name!r} y_prob is not an array")
        elif y_true is not None and len(y_prob) != len(y_true):
            errors.append(f"model {name!r} y_prob length does not match y_true")
        else:
            if not all(_is_finite_number(v) and 0.0 <= v <= 1.0 for v in y_prob):
                errors.append(f"model {name!r} y_prob values are not finite numbers in [0, 1]")
    return errors


MINIMAL_VALID_SEAL = {
    "schema_version": "1.0.0",
    "experiment": "secom-cost-threshold",
    "sealed_before_run": True,
    "dataset": {
        "name": "UCI SECOM",
        "url": "https://example.invalid/secom.zip",
        "class_counts": {"pass_0": 1463, "fail_1": 104},
        "files": {
            "secom.data": {"sha256": "a" * 64, "rows": 1567, "columns": 590},
            "secom_labels.data": {"sha256": "b" * 64, "rows": 1567},
        },
    },
    "splitter": {"class": "RepeatedStratifiedKFold", "n_splits": 10,
                 "n_repeats": 3, "random_state": 0},
    "models": {
        "knn": {"estimator": "KNeighborsClassifier", "params": {}, "random_state": None},
        "decision_tree": {"estimator": "DecisionTreeClassifier", "params": {},
                          "random_state": 0},
        "random_forest": {"estimator": "RandomForestClassifier", "params": {},
                          "random_state": 0},
        "logistic_regression": {"estimator": "LogisticRegression",
                                "params": {"max_iter": 1000}, "random_state": 0},
    },
    "numeric_guards": {"variance_drop_std_below": 1e-12,
                       "correlation_abs_drop_above": 0.95, "zero_division": 0},
}


def validate_seal(data):
    """Validate the pre-registered seal.json."""
    errors = []
    if not isinstance(data, dict):
        return [f"not an object: {type(data).__name__}"]
    for field in ["schema_version", "experiment", "dataset", "splitter", "models", "numeric_guards"]:
        if field not in data:
            errors.append(f"missing required key {field}")
    if data.get("sealed_before_run") is not True:
        errors.append("sealed_before_run is not true")
    splitter = data.get("splitter")
    if isinstance(splitter, dict):
        if (splitter.get("n_splits"), splitter.get("n_repeats"), splitter.get("random_state")) != (10, 3, 0):
            errors.append("splitter is not pinned to n_splits=10, n_repeats=3, random_state=0")
    guards = data.get("numeric_guards")
    if isinstance(guards, dict) and guards.get("zero_division") != 0:
        errors.append("numeric_guards.zero_division is not 0")
    models = data.get("models")
    if isinstance(models, dict):
        if set(models) != {"knn", "decision_tree", "random_forest", "logistic_regression"}:
            errors.append("models must contain exactly knn, decision_tree, random_forest, logistic_regression")
        knn = models.get("knn")
        if isinstance(knn, dict) and knn.get("random_state") is not None:
            errors.append("knn.random_state must be null (estimator does not accept it)")
    return errors


def validate_fold_path(path):
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_fold_record(data)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


def validate_seal_path(path):
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_seal(data)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


def validate_path(path):
    path = pathlib.Path(path)
    parts = path.parts
    if path.name == "seal.json":
        return validate_seal_path(path)
    if len(parts) >= 2 and parts[0] == "results" and parts[1] in ("pilot", "raw"):
        return validate_fold_path(path)
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_record(data, expected_slug=pathlib.Path(path).parent.name)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


MINIMAL_VALID_RECORD = {
    "experiment": "exp-example",
    "schema_version": "1.0.0",
    "title": "Example Experiment",
    "issue": None,
    "date": "2026-01-01",
    "model": "model-under-test",
    "n_per_group": 5,
    "control_condition": "standard instructions",
    "treatment_condition": "modified instructions",
    "rubric_version": "rubric-v1",
    "orchestrator_session": None,
    "repo_head": "0000000000000000000000000000000000000000",
    "experiment_start": "2026-01-01T00:00:00Z",
    "experiment_end": "2026-01-01T01:00:00Z",
    "analyzed_at": "2026-01-02T00:00:00Z",
    "runs": {
        "control_1": {
            "group": "control",
            "session_id": "20260101_01",
            "messages": 10,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "wall_clock_seconds": 30,
            "bytes": 1024,
            "note": None,
        }
    },
    "scores": {"control_1": {"pass": True}},
    "statistical_test": "fisher-exact",
    "conclusion": "No effect observed.",
    "pre_acknowledged_limitations": ["small sample size"],
}


def _mutated(**changes):
    record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    for dotted, value in changes.items():
        parts = dotted.split("__")
        target = record
        for part in parts[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[parts[-1]]
        else:
            target[parts[-1]] = value
    return record


class _Delete:
    pass


_DELETE = _Delete()


def _expect_errors(record, substring, label):
    errors = validate_record(record)
    if not any(substring in error for error in errors):
        print(f"self-test FAILED: {label} not caught: {errors}")
        return False
    return True


def self_test():
    if validate_record(MINIMAL_VALID_RECORD):
        print("self-test FAILED: minimal valid record reported errors")
        return False
    if validate_record(MINIMAL_VALID_RECORD, expected_slug="exp-example"):
        print("self-test FAILED: valid record with matching slug reported errors")
        return False
    cases = [
        (_mutated(title=_DELETE), "missing top-level field title", "missing required key"),
        (_mutated(title=42), "title is not a string", "wrong scalar type"),
        (_mutated(n_per_group=True), "n_per_group is not an integer", "bool not int"),
        (_mutated(n_per_group=1.5), "n_per_group is not an integer", "float not int"),
        (_mutated(date="2026-13-45"), "not a valid calendar date", "invalid date format"),
        (_mutated(date="not-a-date"), "not an ISO date", "non-date string"),
        (_mutated(date="2026-02-30"), "not a valid calendar date", "impossible calendar date"),
        (_mutated(analyzed_at="01/02/2026T00:00:00Z"), "not an ISO 8601 timestamp", "bad timestamp"),
        (
            _mutated(runs__control_1={"group": "placebo"}),
            "not in ['control', 'treatment']",
            "invalid group enum",
        ),
        (
            _mutated(runs__control_1__total_tokens=999),
            "total_tokens != input_tokens + output_tokens",
            "token totals mismatch",
        ),
        (
            _mutated(runs__control_1__messages="ten"),
            "messages is not an integer",
            "non-integer run field",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds="slow"),
            "wall_clock_seconds is not a finite number",
            "non-number wall clock",
        ),
        (
            _mutated(runs__control_1__group=_DELETE),
            "run control_1 missing group",
            "missing run field",
        ),
        (_mutated(scores=[]), "scores is not an object", "scores wrong container"),
        (
            _mutated(scores={"control_1": "pass"}),
            "scores[control_1] is not an object",
            "score entry not object",
        ),
        (
            _mutated(scores={"unknown-run": {"pass": True}}),
            "does not match any run ID",
            "unknown scores key",
        ),
        (
            _mutated(pre_acknowledged_limitations=[1, 2]),
            "not an array of strings",
            "non-string limitation",
        ),
        ([MINIMAL_VALID_RECORD], "not an object: list", "array top level"),
        ("not-an-object", "not an object: str", "scalar top level"),
        (
            _mutated(runs__control_1__group=[]),
            "run control_1 group is not a string",
            "non-hashable group value",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds=True),
            "wall_clock_seconds is not a finite number",
            "boolean wall clock",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds=-1.5),
            "wall_clock_seconds is negative",
            "negative wall clock",
        ),
        (
            _mutated(runs__control_1__input_tokens=-10),
            "input_tokens is negative",
            "negative input tokens",
        ),
        (
            _mutated(scores={"unknown-run": {"pass": True}}, runs={}),
            "scores key unknown-run does not match any run ID",
            "orphan score key with zero runs",
        ),
        (
            _mutated(runs__control_1__session_id=42),
            "session_id is not a string or null",
            "non-string session_id",
        ),
        (
            _mutated(runs__control_1__bytes="big"),
            "bytes is not an integer or null",
            "non-integer bytes",
        ),
        (
            _mutated(runs__control_1__note=3.14),
            "note is not a string or null",
            "non-string note",
        ),
        (
            _mutated(analyzed_at="2026-01-02T00:00:00"),
            "not an ISO 8601 timestamp",
            "naive timestamp without offset",
        ),
        (
            _mutated(analyzed_at="2026-01-02"),
            "not an ISO 8601 timestamp",
            "date-only timestamp",
        ),
    ]
    for record, substring, label in cases:
        if not _expect_errors(record, substring, label):
            return False
    nan_record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    nan_record["runs"]["control_1"]["wall_clock_seconds"] = float("nan")
    if not _expect_errors(
        nan_record, "wall_clock_seconds is not a finite number", "NaN wall clock"
    ):
        return False
    inf_record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    inf_record["runs"]["control_1"]["wall_clock_seconds"] = float("inf")
    if not _expect_errors(
        inf_record, "wall_clock_seconds is not a finite number", "Infinity wall clock"
    ):
        return False
    accepted = [
        (_mutated(issue=None), "null issue accepted"),
        (_mutated(orchestrator_session=None), "null orchestrator_session accepted"),
        (_mutated(runs__control_1__bytes=None), "null bytes accepted"),
        (_mutated(runs__control_1__note=None), "null note accepted"),
        (_mutated(analyzed_at="2026-01-02T00:00:00+00:00"), "offset timestamp accepted"),
    ]
    for record, label in accepted:
        if validate_record(record):
            print(f"self-test FAILED: {label}: {validate_record(record)}")
            return False
    slug_record = json.loads(json.dumps(MINIMAL_VALID_RECORD))
    slug_record["experiment"] = "exp-other"
    slug_errors = validate_record(slug_record, expected_slug="exp-example")
    if not any("does not match directory slug" in error for error in slug_errors):
        print(f"self-test FAILED: slug mismatch not caught: {slug_errors}")
        return False
    # Discovery mode: missing analysis.json must fail, empty experiments/ passes.
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        missing = base / "experiments" / "exp-missing"
        missing.mkdir(parents=True)
        present = base / "experiments" / "exp-present"
        present.mkdir()
        record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
        record["experiment"] = "exp-present"
        (present / "analysis.json").write_text(json.dumps(record))
        if validate_discovery(base):
            print("self-test FAILED: discovery accepted missing analysis.json")
            return False
        empty_base = pathlib.Path(tempfile.mkdtemp())
        try:
            (empty_base / "experiments").mkdir()
            if not validate_discovery(empty_base):
                print("self-test FAILED: discovery rejected empty experiments dir")
                return False
        finally:
            shutil.rmtree(empty_base)
    # Fold-record schema: one happy path, representative edge cases.
    minimal_fold = {
        "schema_version": "1.0.0",
        "run_kind": "pilot",
        "experiment": "secom-cost-threshold",
        "date": "2026-11-15",
        "splitter": {"class": "RepeatedStratifiedKFold", "n_splits": 10,
                     "n_repeats": 1, "random_state": 0},
        "fold": {"repeat": 0, "split": 0, "index": 0},
        "models": [{
            "model": "knn",
            "wall_clock_seconds": 0.1,
            "metrics": {"accuracy": 0.9, "recall_fail": 0.1,
                        "precision_fail": 0.5, "fn": 5, "fp": 2},
            "features": {"raw": 590, "after_variance": 474, "after_correlation": 284},
            "y_true": [0, 1, 1],
            "y_prob": [0.2, 0.8, 0.0],
        }],
    }
    if validate_fold_record(minimal_fold):
        print(f"self-test FAILED: valid fold record rejected: {validate_fold_record(minimal_fold)}")
        return False
    fold_cases = [
        ({**minimal_fold, "run_kind": "sealed_extra"}, "run_kind is not in", "invalid run_kind"),
        ({**minimal_fold, "models": []}, "models is not a non-empty array", "empty models"),
        (
            {**minimal_fold,
             "models": [{**minimal_fold["models"][0], "y_prob": [0.2, 0.8]}]},
            "y_prob length does not match y_true",
            "y_prob length mismatch",
        ),
        (
            {**minimal_fold,
             "models": [{**minimal_fold["models"][0], "y_prob": [0.2, 1.5, 0.0]}]},
            "y_prob values are not finite numbers in [0, 1]",
            "out-of-range y_prob",
        ),
    ]
    for record, substring, label in fold_cases:
        errors = validate_fold_record(record)
        if not any(substring in error for error in errors):
            print(f"self-test FAILED: fold {label} not caught: {errors}")
            return False
    if not validate_fold_record("not-an-object"):
        print("self-test FAILED: scalar fold top level not caught")
        return False
    if validate_seal(MINIMAL_VALID_SEAL):
        print(f"self-test FAILED: valid seal rejected: {validate_seal(MINIMAL_VALID_SEAL)}")
        return False
    bad_seal = json.loads(json.dumps(MINIMAL_VALID_SEAL))
    bad_seal["splitter"] = {"class": "KFold", "n_splits": 5, "n_repeats": 1, "random_state": 7}
    bad_seal["models"]["knn"]["random_state"] = 0
    seal_errors = validate_seal(bad_seal)
    if not any("splitter is not pinned" in error for error in seal_errors) or not any(
        "knn.random_state" in error for error in seal_errors
    ):
        print(f"self-test FAILED: seal violations not caught: {seal_errors}")
        return False
    print(
        "self-test passed: valid record accepted, each rule rejects its invalid case, discovery flags missing analysis.json"
    )
    return True


def validate_discovery(base):
    base = pathlib.Path(base)
    all_ok = True
    seal = base / "seal.json"
    if seal.is_file() and not validate_seal_path(seal):
        all_ok = False
    for subdir in ("pilot", "raw"):
        records_dir = base / "results" / subdir
        if records_dir.is_dir():
            fold_files = sorted(records_dir.glob("*.json"))
            if not fold_files:
                print(f"Validation error: no fold records in {records_dir}")
                all_ok = False
            for path in fold_files:
                if not validate_fold_path(path):
                    all_ok = False
    experiments_dir = base / "experiments"
    if not experiments_dir.is_dir():
        if all_ok:
            print("No experiments/ directory found; nothing to validate.")
        return all_ok
    exp_dirs = sorted(
        d
        for d in experiments_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if not exp_dirs:
        print("No experiments/* directories found; nothing to validate.")
        return True
    all_ok = True
    for exp_dir in exp_dirs:
        analysis = exp_dir / "analysis.json"
        if not analysis.is_file():
            print(f"Validation error: missing {analysis}")
            all_ok = False
            continue
        if not validate_path(analysis):
            all_ok = False
    return all_ok


def main():
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    file_args = [arg for arg in sys.argv[1:] if arg != "--self-test"]
    if file_args:
        all_ok = all(validate_path(pathlib.Path(arg)) for arg in file_args)
        sys.exit(0 if all_ok else 1)
    sys.exit(0 if validate_discovery(pathlib.Path(".").resolve()) else 1)


if __name__ == "__main__":
    main()
