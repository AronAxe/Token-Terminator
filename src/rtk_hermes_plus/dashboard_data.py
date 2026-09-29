"""Content-free, read-only dashboard over existing TT accounting databases.

No Runtime, tokenizer, provider, vault-content or credential access. Source paths
come only from local configuration, never HTTP parameters. Counters from different
stages are deliberately not summed into an inflated 'tokens saved' figure.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ._version import __version__

# Bounded separately from the per-SQLite-statement deadline.
SNAPSHOT_SECONDS = 3.0

MAX_SOURCES = 64
MAX_CONFIG_BYTES = 131_072


@dataclass(frozen=True)
class Source:
    id: str
    label: str
    vault: Path
    ledger: Path
    billing: str = "auto"
    expected_profile: str | None = None


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
        raise ValueError(
            "source ids must contain 1-80 letters, numbers, dots, dashes or underscores"
        )
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _regular(path):
    return not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file()


def source_for_home(home: Path, name="default") -> Source:
    home = Path(home).expanduser().absolute()
    return Source(
        name,
        name,
        home / "token-terminator/artifacts.sqlite3",
        home / "token-terminator/experiments.sqlite3",
        expected_profile=name,
    )


def configuration(home: Path, config_path: Path | None = None, *, discover=True):
    """Only local operator configuration can add stores or choose price assumptions."""
    home = Path(home).expanduser().absolute()
    config_path = config_path or home / "token-terminator/dashboard.json"
    obj = {}
    if config_path.is_symlink():
        raise ValueError("symlinked dashboard configuration is not supported")
    if config_path.exists():
        if not _regular(config_path) or config_path.stat().st_size > MAX_CONFIG_BYTES:
            raise ValueError("invalid dashboard configuration file")
        obj = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or set(obj) - {"sources", "rates"}:
            raise ValueError("dashboard configuration supports only sources and rates")
    sources = []
    if "sources" in obj:
        if (
            not isinstance(obj["sources"], list)
            or not 1 <= len(obj["sources"]) <= MAX_SOURCES
        ):
            raise ValueError("dashboard requires 1-64 explicitly configured sources")
        for item in obj["sources"]:
            if not isinstance(item, dict) or set(item) - {
                "id",
                "label",
                "home",
                "vault",
                "ledger",
                "billing",
            }:
                raise ValueError("invalid dashboard source")
            name = _name(item.get("id"))
            label = item.get("label", name)
            if not isinstance(label, str) or not 1 <= len(label) <= 80:
                raise ValueError("invalid source label")
            billing = item.get("billing", "auto")
            if billing not in {"auto", "api", "subscription", "unknown"}:
                raise ValueError("invalid billing mode")
            base = Path(item.get("home", home)).expanduser().absolute()
            sources.append(
                Source(
                    name,
                    label,
                    Path(item.get("vault", base / "token-terminator/artifacts.sqlite3"))
                    .expanduser()
                    .absolute(),
                    Path(
                        item.get(
                            "ledger", base / "token-terminator/experiments.sqlite3"
                        )
                    )
                    .expanduser()
                    .absolute(),
                    billing,
                )
            )
    else:
        name = home.name if home.parent.name == "profiles" else "default"
        sources = [source_for_home(home, _name(name))]
        profiles = home / "profiles"
        if discover and profiles.is_dir() and not profiles.is_symlink():
            children = sorted(profiles.iterdir())
            for child in children:
                if (
                    child.is_dir()
                    and not child.is_symlink()
                    and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", child.name)
                ):
                    sources.append(source_for_home(child, child.name))
        if len(sources) > MAX_SOURCES:
            raise ValueError(
                "more than 64 profiles; configure an explicit bounded source list"
            )
    if len({s.id for s in sources}) != len(sources):
        raise ValueError("duplicate dashboard source id")
    # A shared DB cannot safely be credited in full to multiple bots. Reject,
    # including hard links, rather than double-count or guess legacy attribution.
    seen = set()
    for source in sources:
        for path in (source.vault, source.ledger):
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError("symlinked dashboard database paths are not supported")
            identity = (
                (path.stat().st_dev, path.stat().st_ino) if path.exists() else str(path)
            )
            if identity in seen:
                raise ValueError(
                    "shared or duplicate databases need one source, not duplicate profile totals"
                )
            seen.add(identity)
    rates = obj.get("rates", {})
    if not isinstance(rates, dict) or len(rates) > 128:
        raise ValueError("invalid rate cards")
    for model, rate in rates.items():
        if (
            not isinstance(model, str)
            or not 1 <= len(model) <= 256
            or not isinstance(rate, dict)
        ):
            raise ValueError("invalid model rate card")
        if set(rate) - {"input_usd_per_million", "output_usd_per_million", "as_of"}:
            raise ValueError("rate cards use USD per million input/output tokens")
        for key in ("input_usd_per_million", "output_usd_per_million"):
            if key in rate and (_number(rate[key]) is None or rate[key] > 1_000_000):
                raise ValueError("invalid nonnegative per-million rate")
        if (
            not isinstance(rate.get("as_of", ""), str)
            or len(rate.get("as_of", "")) > 80
        ):
            raise ValueError("invalid rate-card date")
    return sources, rates


@contextmanager
def read_database(path: Path):
    """Bounded read-only snapshots, including live WAL; do not use immutable=1."""
    if not _regular(path):
        raise FileNotFoundError("accounting database unavailable")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.15)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        deadline = time.monotonic() + 0.35
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 5000)
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.close()


def _table(db, name):
    # Views are not trusted accounting tables.
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    )


def _measured(source):
    with read_database(source.vault) as db:
        if not _table(db, "request_token_metrics"):
            return None
        rows = [
            dict(r)
            for r in db.execute("""SELECT model, COUNT(*) AS requests,
            SUM(raw_tokens) AS raw, SUM(final_tokens) AS final,
            SUM(saved_tokens) AS saved, MAX(measured_at) AS updated
            FROM request_token_metrics
            WHERE typeof(raw_tokens)='integer' AND typeof(final_tokens)='integer'
              AND typeof(saved_tokens)='integer'
              AND raw_tokens >= final_tokens AND final_tokens >= 0
              AND saved_tokens = raw_tokens-final_tokens
            GROUP BY model ORDER BY model LIMIT 256""")
        ]
        total_rows = db.execute(
            "SELECT COUNT(DISTINCT model) FROM request_token_metrics"
        ).fetchone()[0]
        if total_rows > 256:
            raise ValueError("model grouping limit exceeded")
        invalid = db.execute("""SELECT COUNT(*) FROM request_token_metrics WHERE
            typeof(raw_tokens)!='integer' OR typeof(final_tokens)!='integer'
            OR typeof(saved_tokens)!='integer' OR raw_tokens < final_tokens
            OR final_tokens < 0 OR saved_tokens != raw_tokens-final_tokens""").fetchone()[
            0
        ]
        trend = [
            dict(r)
            for r in db.execute("""SELECT substr(measured_at,1,10) AS day,
            SUM(saved_tokens) AS saved FROM request_token_metrics
            WHERE typeof(raw_tokens)='integer' AND typeof(final_tokens)='integer'
              AND typeof(saved_tokens)='integer'
              AND raw_tokens >= final_tokens AND final_tokens >= 0
              AND saved_tokens=raw_tokens-final_tokens
              AND measured_at >= date('now','-13 days')
            GROUP BY day ORDER BY day""")
        ]
        fallback = {"requests": 0, "estimated_saved": 0}
        if _table(db, "request_metrics"):
            r = db.execute("""SELECT COUNT(*) AS n, COALESCE(SUM(MAX(0,r.end_to_end_saved_chars)),0) AS chars
                FROM request_metrics r LEFT JOIN request_token_metrics t
                  ON r.session_id=t.session_id AND r.request_id=t.request_id
                WHERE r.end_to_end_measured=1 AND t.request_id IS NULL""").fetchone()
            fallback = {"requests": r["n"], "estimated_saved": round(r["chars"] / 4)}
    return {
        "models": rows,
        "trend": trend,
        "fallback": fallback,
        "invalid_rows": invalid,
    }


class AttributionError(ValueError):
    """A legacy store cannot be honestly assigned to this isolated profile."""


def _usage(source):
    with read_database(source.ledger) as db:
        if not _table(db, "sessions"):
            return None
        names = [
            r[0]
            for r in db.execute(
                "SELECT DISTINCT profile FROM sessions WHERE profile!='' LIMIT 65"
            )
        ]
        if len(names) > 1 or (
            source.expected_profile is not None
            and any(n != source.expected_profile for n in names)
        ):
            raise AttributionError("shared or mismatched profile accounting")
        # Session totals are authoritative here. Adding turns would count twice.
        row = dict(
            db.execute("""SELECT COUNT(*) AS sessions,
            SUM(input_tokens) AS input, SUM(output_tokens) AS output,
            SUM(cache_read_tokens) AS cache_read, SUM(cache_write_tokens) AS cache_write,
            SUM(reasoning_tokens) AS reasoning, SUM(api_call_count) AS calls,
            SUM(recovery_reads) AS recovery_reads, SUM(completed_turns) AS completed,
            SUM(failed_turns) AS failed, MAX(last_seen_at) AS updated,
            SUM(actual_cost_usd) AS actual_cost_usd, COUNT(actual_cost_usd) AS priced_sessions,
            SUM(estimated_cost_usd) AS estimated_cost_usd,
            SUM(api_equivalent_cost_usd) AS ledger_api_equivalent_usd,
            SUM(CASE WHEN contamination_reason='accounting unavailable' THEN 1 ELSE 0 END) AS unavailable_sessions
            FROM sessions""").fetchone()
        )
        modes = [
            str(r[0])
            for r in db.execute(
                "SELECT DISTINCT billing_mode FROM sessions WHERE billing_mode!='' LIMIT 32"
            )
        ]
        statuses = [
            str(r[0])
            for r in db.execute(
                "SELECT DISTINCT cost_status FROM sessions WHERE cost_status!='' LIMIT 32"
            )
        ]
        # Multi-model / unavailable sessions cannot be priced at the last model.
        model_usage = [
            dict(r)
            for r in db.execute("""SELECT last_model AS model,
            SUM(input_tokens) AS input, SUM(output_tokens) AS output,
            COUNT(*) AS sessions FROM sessions WHERE initial_model=last_model
            AND last_model!='' AND contaminated=0
            GROUP BY last_model ORDER BY last_model LIMIT 257""")
        ]
        if len(model_usage) > 256:
            raise ValueError("usage model grouping limit exceeded")
    if not row["sessions"]:
        return None
    for key, value in row.items():
        if key != "updated" and value is not None and _number(value) is None:
            raise ValueError("invalid accounting value")
    # The ledger uses zero placeholders when host accounting is absent; that is
    # not observed zero consumption. Surface it as unknown, not a free session.
    if row["unavailable_sessions"] == row["sessions"]:
        for key in (
            "input",
            "output",
            "cache_read",
            "cache_write",
            "reasoning",
            "calls",
            "actual_cost_usd",
            "estimated_cost_usd",
            "ledger_api_equivalent_usd",
        ):
            row[key] = None
    row["model_usage"] = model_usage
    row["billing_modes"] = modes
    row["cost_statuses"] = statuses
    return row


def _billing(source, usage):
    if source.billing != "auto":
        return source.billing
    modes = set(usage.get("billing_modes", [])) if usage else set()
    statuses = set(usage.get("cost_statuses", [])) if usage else set()
    if modes and modes <= {
        "subscription",
        "subscription_included",
        "oauth",
        "included",
    }:
        return "subscription"
    if statuses == {"included"}:
        return "subscription"
    if modes and modes <= {"api", "metered", "api_metered", "payg", "pay_as_you_go"}:
        return "api"
    return "mixed" if len(modes) > 1 else "unknown"


def profile_summary(source: Source, rates: dict, *, read_enabled=True) -> dict:
    issues = []
    measurement = usage = None
    attribution_ok = True
    for name, read in (("usage", _usage), ("measurement", _measured)):
        try:
            value = read(source) if read_enabled and attribution_ok else None
            if value is None:
                issues.append(
                    name + ("_missing" if read_enabled else "_budget_exceeded")
                )
        except AttributionError:
            value = None
            attribution_ok = False
            issues.append("profile_attribution_ambiguous")
        except (OSError, sqlite3.Error, ValueError, TypeError):
            value = None
            issues.append(name + "_unavailable")
        if name == "measurement":
            measurement = value
        else:
            usage = value
    rows = measurement["models"] if measurement else []
    counts = {
        key: sum(r[key] for r in rows) for key in ("requests", "raw", "final", "saved")
    }
    priced_saved = 0
    equivalent_saved = 0.0
    for row in rows:
        rate = rates.get(row["model"], {})
        input_rate = rate.get("input_usd_per_million")
        row["rate_as_of"] = rate.get("as_of")
        row["input_usd_per_million"] = input_rate
        row["output_usd_per_million"] = rate.get("output_usd_per_million")
        row["saved_api_equivalent_usd"] = (
            None if input_rate is None else row["saved"] * input_rate / 1_000_000
        )
        if input_rate is not None:
            priced_saved += row["saved"]
            equivalent_saved += row["saved_api_equivalent_usd"]
    fallback = (
        measurement["fallback"]
        if measurement
        else {"requests": 0, "estimated_saved": None}
    )
    measured = counts["requests"]
    if measurement and measurement["invalid_rows"]:
        issues.append("invalid_measurement_rows_excluded")
    billing = _billing(source, usage)
    usage_value = {}
    for direction in ("input", "output"):
        covered = [
            r
            for r in (usage["model_usage"] if usage else [])
            if rates.get(r["model"], {}).get(direction + "_usd_per_million") is not None
        ]
        priced = sum(r[direction] for r in covered)
        value = sum(
            r[direction] * rates[r["model"]][direction + "_usd_per_million"] / 1_000_000
            for r in covered
        )
        observed = usage[direction] if usage else None
        usage_value[direction + "_api_equivalent_usd"] = value if covered else None
        usage_value[direction + "_priced_tokens"] = priced
        usage_value[direction + "_price_coverage_pct"] = (
            round(100 * priced / observed, 2) if observed else None
        )
        usage_value[direction + "_weighted_usd_per_million"] = (
            value * 1_000_000 / priced if priced else None
        )
    return {
        "id": source.id,
        "label": source.label,
        "billing": billing,
        "available": measurement is not None or usage is not None,
        "attribution": "isolated_store" if attribution_ok else "ambiguous_legacy_store",
        "measurement_available": measurement is not None,
        "usage_available": usage is not None,
        "input": {
            "saved": counts["saved"] if measurement is not None else None,
            "before": counts["raw"] if measurement is not None else None,
            "prepared": counts["final"] if measurement is not None else None,
            "observed": usage["input"] if usage else None,
            "reduction_pct": round(100 * counts["saved"] / counts["raw"], 2)
            if counts["raw"]
            else None,
            "measured_requests": measured,
            "estimated_saved": fallback["estimated_saved"],
            "estimated_requests": fallback["requests"],
            "exact_coverage_pct": round(
                100 * measured / (measured + fallback["requests"]), 2
            )
            if measured + fallback["requests"]
            else None,
        },
        "output": {
            "observed": usage["output"] if usage else None,
            "saved": None,
            "savings_status": "no_counterfactual",
        },
        "usage": usage,
        "value": {
            "currency": "USD",
            "saved_api_equivalent_usd": equivalent_saved
            if priced_saved
            else (
                0.0
                if rows and all(r["input_usd_per_million"] is not None for r in rows)
                else None
            ),
            "priced_saved_tokens": priced_saved,
            "price_coverage_pct": round(100 * priced_saved / counts["saved"], 2)
            if counts["saved"]
            else None,
            "weighted_input_usd_per_million": equivalent_saved
            * 1_000_000
            / priced_saved
            if priced_saved
            else None,
            "actual_cost_usd": usage["actual_cost_usd"] if usage else None,
            "actual_cost_coverage_pct": round(
                100 * usage["priced_sessions"] / usage["sessions"], 2
            )
            if usage
            else None,
            **usage_value,
            "cash_savings_usd": None,
            "jev_cost_usd": None,
            "net_savings_usd": None,
            "meaning": "API-equivalent only; subscription fee unchanged"
            if billing == "subscription"
            else "Rate-card estimate; not an invoice or net savings",
        },
        "models": rows,
        "trend": measurement["trend"] if measurement else [],
        "issues": issues,
    }


def snapshot(sources: list[Source], rates: dict, *, profile: str | None = None):
    if profile is not None:
        sources = [s for s in sources if s.id == profile]
        if not sources:
            raise KeyError("unknown profile")
    deadline = time.monotonic() + SNAPSHOT_SECONDS
    profiles = [
        profile_summary(source, rates, read_enabled=time.monotonic() < deadline)
        for source in sources
    ]
    return summary_from_profiles(profiles)


def summary_from_profiles(profiles, *, generated_at=None):
    def total(section, key):
        values = [p[section][key] for p in profiles if p[section][key] is not None]
        return sum(values) if values else None

    return {
        "schema_version": 1,
        "version": __version__,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "window": "all_recorded_history",
        "profiles": profiles,
        "totals": {
            "input_saved": total("input", "saved"),
            "input_prepared": total("input", "prepared"),
            "input_observed": total("input", "observed"),
            "output_observed": total("output", "observed"),
            "output_saved": None,
            "saved_api_equivalent_usd": total("value", "saved_api_equivalent_usd"),
            "actual_cost_usd": total("value", "actual_cost_usd"),
            "input_api_equivalent_usd": total("value", "input_api_equivalent_usd"),
            "output_api_equivalent_usd": total("value", "output_api_equivalent_usd"),
            "measured_requests": sum(p["input"]["measured_requests"] for p in profiles),
            "available_profiles": sum(p["available"] for p in profiles),
            "unavailable_profiles": sum(not p["available"] for p in profiles),
        },
        "notes": [
            "Input savings measure prepared canonical requests, not provider-billed tokens or guaranteed sends.",
            "Observed usage is the TT ledger's host-reported session delta since attachment; updates at lifecycle hooks, not per streamed token.",
            "Output savings have no measured counterfactual. Tool-output compaction is input reduction, not generated-output savings.",
            "Usage valuation covers single-model, uncontaminated sessions with configured rates only. Input/output rates are separate; averages are token-weighted. Unknown and mixed-model usage is not priced.",
            "Rate-card values are gross API equivalents; cache effects, JEV, recovery and subscription quotas are not inferred.",
            "Totals cover available records only. No model calls, credential reads or source-content reads power this dashboard.",
        ],
    }
