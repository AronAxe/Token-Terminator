from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))


def re_sub_once(path: str, pattern: str, replacement: str, *, flags: int = 0) -> None:
    text = read(path)
    new, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{path}: regex expected one occurrence: {pattern[:100]!r}")
    write(path, new)


# ---------------------------------------------------------------------------
# Version: this is a hardening patch release, not a feature-number jump.
# ---------------------------------------------------------------------------
replace_once("src/rtk_hermes_plus/_version.py", '__version__ = "0.5.0"', '__version__ = "0.5.1"')
replace_once("pyproject.toml", 'version = "0.5.0"', 'version = "0.5.1"')
replace_once("Cargo.toml", 'version = "0.5.0"', 'version = "0.5.1"')

# ---------------------------------------------------------------------------
# 1, 2, 6, 9: config invariants, retention controls, one canonical default,
# and an optional pinned RTK binary.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/config.py",
    '    enabled_backends: tuple[str, ...] = ("local",)\n    cache_ttl_seconds: int = 600\n',
    '    enabled_backends: tuple[str, ...] = ("local",)\n    rtk_path: Path | None = None\n    cache_ttl_seconds: int = 600\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '    vault_max_bytes: int = 536_870_912\n    inline_lease_exposures: int = 1\n',
    '    vault_max_bytes: int = 536_870_912\n    vault_high_water_pct: int = 90\n    vault_low_water_pct: int = 80\n    inline_lease_exposures: int = 1\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '        for name in ("ledger_path", "state_db_path", "db_path"):\n            object.__setattr__(self, name, Path(getattr(self, name)).expanduser())\n        for name in ("inline_lease_exposures", "graph_context_chars"):\n',
    '        for name in ("ledger_path", "state_db_path", "db_path"):\n            object.__setattr__(self, name, Path(getattr(self, name)).expanduser())\n        if self.rtk_path is not None:\n            object.__setattr__(self, "rtk_path", Path(self.rtk_path).expanduser())\n        for name in (\n            "inline_lease_exposures",\n            "graph_context_chars",\n            "context_collapse_after_turns",\n            "context_inline_recent_turns",\n        ):\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '        if self.min_artifact_chars > self.max_artifact_chars:\n            raise ValueError("min_artifact_chars must not exceed max_artifact_chars")\n',
    '        if self.min_artifact_chars > self.max_artifact_chars:\n            raise ValueError("min_artifact_chars must not exceed max_artifact_chars")\n        if not 0 <= self.vault_low_water_pct < self.vault_high_water_pct <= 100:\n            raise ValueError("vault watermarks must satisfy 0 <= low < high <= 100")\n        if (\n            self.context_collapse_after_turns > 0\n            and self.context_collapse_after_turns < self.context_inline_recent_turns\n        ):\n            raise ValueError(\n                "context_collapse_after_turns must be 0 or at least "\n                "context_inline_recent_turns"\n            )\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '    config = Config(\n',
    '    rtk_raw = _env("TOKEN_TERMINATOR_RTK_PATH")\n    context_inline_recent_turns = _integer(\n        "TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS", 5, minimum=0\n    )\n    context_collapse_after_turns = _integer(\n        "TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS", 6, minimum=0\n    )\n    if (\n        context_collapse_after_turns > 0\n        and context_collapse_after_turns < context_inline_recent_turns\n    ):\n        context_collapse_after_turns = context_inline_recent_turns\n    vault_high_water_pct = _integer(\n        "TOKEN_TERMINATOR_VAULT_HIGH_WATER_PCT", 90, minimum=1, maximum=100\n    )\n    vault_low_water_pct = _integer(\n        "TOKEN_TERMINATOR_VAULT_LOW_WATER_PCT", 80, minimum=0, maximum=99\n    )\n    if vault_low_water_pct >= vault_high_water_pct:\n        vault_low_water_pct = max(0, vault_high_water_pct - 10)\n\n    config = Config(\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '        enabled_backends=backends,\n        cache_ttl_seconds=_integer(\n',
    '        enabled_backends=backends,\n        rtk_path=Path(rtk_raw).expanduser() if rtk_raw else None,\n        cache_ttl_seconds=_integer(\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '        vault_max_bytes=_integer(\n            "TOKEN_TERMINATOR_VAULT_MAX_BYTES",\n            536_870_912,\n            minimum=1,\n            maximum=100_000_000_000,\n        ),\n        inline_lease_exposures=_integer(\n',
    '        vault_max_bytes=_integer(\n            "TOKEN_TERMINATOR_VAULT_MAX_BYTES",\n            536_870_912,\n            minimum=1,\n            maximum=100_000_000_000,\n        ),\n        vault_high_water_pct=vault_high_water_pct,\n        vault_low_water_pct=vault_low_water_pct,\n        inline_lease_exposures=_integer(\n',
)
replace_once(
    "src/rtk_hermes_plus/config.py",
    '        context_collapse_after_turns=_integer(\n            "TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS",\n            6,\n            minimum=0,\n        ),\n        context_inline_recent_turns=_integer(\n            "TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS",\n            3,\n            minimum=0,\n        ),\n',
    '        context_collapse_after_turns=context_collapse_after_turns,\n        context_inline_recent_turns=context_inline_recent_turns,\n',
)

# Defensive compactor invariant even for direct ContextCompactor construction.
replace_once(
    "src/rtk_hermes_plus/context_compactor.py",
    '        self.collapse_after_turns = max(0, int(collapse_after_turns))\n        self.inline_recent_turns = max(0, int(inline_recent_turns))\n',
    '        self.inline_recent_turns = max(0, int(inline_recent_turns))\n        collapse_after_turns = max(0, int(collapse_after_turns))\n        self.collapse_after_turns = (\n            max(collapse_after_turns, self.inline_recent_turns)\n            if collapse_after_turns > 0\n            else 0\n        )\n',
)

# ---------------------------------------------------------------------------
# 1, 3, 8, 9: capacity-managed vault, Unicode-safe search, schema-owned
# temporal snapshots, safer permissions, and explicit exposure accounting.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '        max_vault_bytes: int = 536_870_912,\n        max_page_chars: int = 20_000,\n    ):\n        self.path = Path(path).expanduser()\n        self.max_artifact_chars = max(1, int(max_artifact_chars))\n        self.max_vault_bytes = max(1, int(max_vault_bytes))\n        self.max_page_chars = max(1, int(max_page_chars))\n        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)\n        if os.name == "posix":\n            os.chmod(self.path.parent, 0o700)\n',
    '        max_vault_bytes: int = 536_870_912,\n        max_page_chars: int = 20_000,\n        high_water_pct: int = 90,\n        low_water_pct: int = 80,\n    ):\n        self.path = Path(path).expanduser()\n        self.max_artifact_chars = max(1, int(max_artifact_chars))\n        self.max_vault_bytes = max(1, int(max_vault_bytes))\n        self.max_page_chars = max(1, int(max_page_chars))\n        self.high_water_pct = min(100, max(1, int(high_water_pct)))\n        self.low_water_pct = min(self.high_water_pct - 1, max(0, int(low_water_pct)))\n        parent_existed = self.path.parent.exists()\n        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)\n        if os.name == "posix" and not parent_existed:\n            os.chmod(self.path.parent, 0o700)\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '        conn.execute("PRAGMA synchronous=NORMAL")\n        return conn\n',
    '        conn.execute("PRAGMA synchronous=NORMAL")\n        conn.create_function(\n            "tt_casefold",\n            1,\n            lambda value: str(value or "").casefold(),\n            deterministic=True,\n        )\n        return conn\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '                CREATE TABLE IF NOT EXISTS artifact_exposures (\n                    session_id TEXT NOT NULL,\n                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),\n                    request_id TEXT NOT NULL,\n                    inline INTEGER NOT NULL CHECK(inline IN (0, 1)),\n                    exposed_at TEXT NOT NULL,\n                    PRIMARY KEY(session_id, artifact_id, request_id)\n                );\n\n                CREATE TABLE IF NOT EXISTS graph_events (\n',
    '                CREATE TABLE IF NOT EXISTS artifact_exposures (\n                    session_id TEXT NOT NULL,\n                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),\n                    request_id TEXT NOT NULL,\n                    inline INTEGER NOT NULL CHECK(inline IN (0, 1)),\n                    exposed_at TEXT NOT NULL,\n                    PRIMARY KEY(session_id, artifact_id, request_id)\n                );\n\n                CREATE TABLE IF NOT EXISTS terminal_snapshots (\n                    state_key TEXT PRIMARY KEY,\n                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),\n                    command TEXT NOT NULL,\n                    cwd TEXT NOT NULL,\n                    backend TEXT NOT NULL,\n                    session_scope TEXT NOT NULL DEFAULT \'\',\n                    updated_at TEXT NOT NULL\n                );\n\n                CREATE TABLE IF NOT EXISTS vault_meta (\n                    key TEXT PRIMARY KEY,\n                    value INTEGER NOT NULL\n                );\n\n                CREATE TABLE IF NOT EXISTS graph_events (\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '            conn.execute(\n                """\n                CREATE TRIGGER IF NOT EXISTS invalidate_request_metric_end_to_end\n',
    '            total_bytes = int(\n                conn.execute("SELECT COALESCE(SUM(byte_count), 0) FROM artifacts").fetchone()[0]\n            )\n            conn.execute(\n                "INSERT INTO vault_meta(key, value) VALUES(\'total_artifact_bytes\', ?) "\n                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",\n                (total_bytes,),\n            )\n            conn.execute(\n                "INSERT OR IGNORE INTO vault_meta(key, value) VALUES(\'pruned_artifacts\', 0)"\n            )\n            conn.execute(\n                "INSERT OR IGNORE INTO vault_meta(key, value) VALUES(\'pruned_bytes\', 0)"\n            )\n\n            conn.execute(\n                """\n                CREATE TRIGGER IF NOT EXISTS invalidate_request_metric_end_to_end\n',
)
insert_methods = '''    @staticmethod
    def _meta_int(conn: sqlite3.Connection, key: str) -> int:
        row = conn.execute("SELECT value FROM vault_meta WHERE key=?", (key,)).fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _set_meta_int(conn: sqlite3.Connection, key: str, value: int) -> None:
        conn.execute(
            "INSERT INTO vault_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, max(0, int(value))),
        )

    def _prune_for_insert(
        self, conn: sqlite3.Connection, *, current_bytes: int, incoming_bytes: int
    ) -> int:
        high_bytes = max(1, self.max_vault_bytes * self.high_water_pct // 100)
        if current_bytes + incoming_bytes <= high_bytes:
            return current_bytes
        low_bytes = self.max_vault_bytes * self.low_water_pct // 100
        target_before_insert = max(0, low_bytes - incoming_bytes)
        rows = conn.execute(
            """
            SELECT a.artifact_id, a.byte_count,
                   COALESCE(MAX(o.observed_at), a.created_at) AS last_observed
            FROM artifacts a
            LEFT JOIN artifact_observations o ON o.artifact_id=a.artifact_id
            WHERE NOT EXISTS (
                SELECT 1 FROM terminal_snapshots t
                WHERE t.artifact_id=a.artifact_id
            )
            GROUP BY a.artifact_id
            ORDER BY last_observed ASC, a.created_at ASC, a.artifact_id ASC
            """
        ).fetchall()
        removed_artifacts = 0
        removed_bytes = 0
        for row in rows:
            if current_bytes <= target_before_insert:
                break
            artifact_id = str(row["artifact_id"])
            byte_count = int(row["byte_count"])
            conn.execute("DELETE FROM artifact_exposures WHERE artifact_id=?", (artifact_id,))
            conn.execute("DELETE FROM artifact_observations WHERE artifact_id=?", (artifact_id,))
            conn.execute("DELETE FROM artifacts WHERE artifact_id=?", (artifact_id,))
            current_bytes = max(0, current_bytes - byte_count)
            removed_artifacts += 1
            removed_bytes += byte_count
        if removed_artifacts:
            self._set_meta_int(conn, "total_artifact_bytes", current_bytes)
            self._set_meta_int(
                conn,
                "pruned_artifacts",
                self._meta_int(conn, "pruned_artifacts") + removed_artifacts,
            )
            self._set_meta_int(
                conn,
                "pruned_bytes",
                self._meta_int(conn, "pruned_bytes") + removed_bytes,
            )
        return current_bytes

    def vault_usage(self) -> dict[str, int]:
        with self.connection() as conn:
            current = self._meta_int(conn, "total_artifact_bytes")
            pruned_artifacts = self._meta_int(conn, "pruned_artifacts")
            pruned_bytes = self._meta_int(conn, "pruned_bytes")
        return {
            "vault_bytes": current,
            "vault_capacity_bytes": self.max_vault_bytes,
            "vault_high_water_bytes": self.max_vault_bytes * self.high_water_pct // 100,
            "vault_low_water_bytes": self.max_vault_bytes * self.low_water_pct // 100,
            "vault_usage_pct_x1000": round(current / self.max_vault_bytes * 100_000),
            "vault_pruned_artifacts": pruned_artifacts,
            "vault_pruned_bytes": pruned_bytes,
        }

    def record_exposure(
        self,
        *,
        session_id: str,
        artifact_id: str,
        request_id: str,
        inline: bool = True,
    ) -> None:
        with self.connection(write=True) as conn:
            conn.execute(
                """
                INSERT INTO artifact_exposures(
                    session_id, artifact_id, request_id, inline, exposed_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, artifact_id, request_id) DO UPDATE SET
                    inline=MAX(artifact_exposures.inline, excluded.inline),
                    exposed_at=excluded.exposed_at
                """,
                (
                    str(session_id or ""),
                    str(artifact_id),
                    str(request_id or ""),
                    int(bool(inline)),
                    _utc_now(),
                ),
            )

'''
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '    def put_artifact(\n',
    insert_methods + '    def put_artifact(\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '            if existing is None:\n                current_bytes = int(\n                    conn.execute(\n                        "SELECT COALESCE(SUM(byte_count), 0) FROM artifacts"\n                    ).fetchone()[0]\n                )\n                if current_bytes + len(encoded) > self.max_vault_bytes:\n                    raise VaultCapacityError(\n                        f"artifact vault capacity would exceed {self.max_vault_bytes} bytes"\n                    )\n                conn.execute(\n',
    '            if existing is None:\n                current_bytes = self._meta_int(conn, "total_artifact_bytes")\n                current_bytes = self._prune_for_insert(\n                    conn, current_bytes=current_bytes, incoming_bytes=len(encoded)\n                )\n                if current_bytes + len(encoded) > self.max_vault_bytes:\n                    raise VaultCapacityError(\n                        f"artifact vault capacity would exceed {self.max_vault_bytes} bytes"\n                    )\n                conn.execute(\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '                )\n            else:\n                artifact_id = existing["artifact_id"]\n',
    '                )\n                self._set_meta_int(\n                    conn, "total_artifact_bytes", current_bytes + len(encoded)\n                )\n            else:\n                artifact_id = existing["artifact_id"]\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '        needle = str(query or "").strip().lower()\n',
    '        needle = str(query or "").strip().casefold()\n',
)
text = read("src/rtk_hermes_plus/storage.py")
text = text.replace("instr(lower(a.content), ?)", "instr(tt_casefold(a.content), ?)")
text = text.replace("instr(lower(a.tool_name), ?)", "instr(tt_casefold(a.tool_name), ?)")
text = text.replace("instr(lower(matched.tool_name), ?)", "instr(tt_casefold(matched.tool_name), ?)")
write("src/rtk_hermes_plus/storage.py", text)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '        "any_failed_open_requests",\n    )\n',
    '        "any_failed_open_requests",\n        "vault_bytes",\n        "vault_capacity_bytes",\n        "vault_high_water_bytes",\n        "vault_low_water_bytes",\n        "vault_usage_pct_x1000",\n        "vault_pruned_artifacts",\n        "vault_pruned_bytes",\n    )\n',
)
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '        with self.connection() as conn:\n            return {\n                name: int(conn.execute(sql).fetchone()[0])\n                for name, sql in queries.items()\n            }\n',
    '        with self.connection() as conn:\n            result = {\n                name: int(conn.execute(sql).fetchone()[0])\n                for name, sql in queries.items()\n            }\n        result.update(self.vault_usage())\n        return result\n',
)

# Wire retention policy into the production store.
replace_once(
    "src/rtk_hermes_plus/compress.py",
    '                max_vault_bytes=config.vault_max_bytes,\n                max_page_chars=config.max_artifact_page_chars,\n',
    '                max_vault_bytes=config.vault_max_bytes,\n                max_page_chars=config.max_artifact_page_chars,\n                high_water_pct=config.vault_high_water_pct,\n                low_water_pct=config.vault_low_water_pct,\n',
)

# ---------------------------------------------------------------------------
# 4, 9, 10: cwd-aware rewrite cache, pinned RTK path, and avoid expanding
# repeated-line runs that are shorter in their original form.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/rewrite.py",
    '        self.cache = RewriteCache(config.cache_size, config.cache_ttl_seconds)\n        self.rtk_path = shutil.which("rtk")\n',
    '        self.cache = RewriteCache(config.cache_size, config.cache_ttl_seconds)\n        self.rtk_path = (\n            str(config.rtk_path) if config.rtk_path is not None else shutil.which("rtk")\n        )\n',
)
replace_once(
    "src/rtk_hermes_plus/rewrite.py",
    '    @property\n    def available(self) -> bool:\n        return self.rtk_path is not None\n\n    def _result_from_output(\n',
    '    @property\n    def available(self) -> bool:\n        return self.rtk_path is not None\n\n    @staticmethod\n    def _cache_key(command: str, cwd: Path) -> str:\n        return f"{cwd.expanduser().resolve()}\\0{command}"\n\n    def _result_from_output(\n',
)
replace_once(
    "src/rtk_hermes_plus/rewrite.py",
    '        command: str,\n        *,\n        stdout: str,\n',
    '        command: str,\n        *,\n        cache_key: str,\n        stdout: str,\n',
)
replace_once(
    "src/rtk_hermes_plus/rewrite.py",
    '        self.cache.put(command, result)\n',
    '        self.cache.put(cache_key, result)\n',
)
text = read("src/rtk_hermes_plus/rewrite.py")
text = text.replace(
    '        cached = self.cache.get(command)\n',
    '        cache_key = self._cache_key(command, cwd)\n        cached = self.cache.get(cache_key)\n',
)
text = text.replace(
    '                command,\n                stdout=',
    '                command,\n                cache_key=cache_key,\n                stdout=',
)
write("src/rtk_hermes_plus/rewrite.py", text)
replace_once(
    "src/rtk_hermes_plus/compress.py",
    'def _collapsed_line(line: str, count: int) -> str:\n    return f"{line}  [repeated ×{count}]" if count > 2 else "\\n".join([line] * count)\n',
    'def _collapsed_line(line: str, count: int) -> str:\n    original = "\\n".join([line] * count)\n    if count <= 2:\n        return original\n    collapsed = f"{line}  [repeated ×{count}]"\n    return collapsed if len(collapsed) < len(original) else original\n',
)

# Recovery note percentages must include the note itself. Iterate to a stable
# displayed percentage because the percentage text slightly changes its length.
replace_once(
    "src/rtk_hermes_plus/compress.py",
    'def _recovery_note(raw_chars: int, compact_chars: int, artifact_id: str) -> str:\n    savings = (\n        round((raw_chars - compact_chars) / raw_chars * 100, 1) if raw_chars else 0.0\n    )\n    return (\n        f"[Token Terminator: {savings}% fewer characters; "\n        f"full artifact={artifact_id}; recover with token_terminator action=artifact_get]"\n    )\n',
    'def _recovery_note(raw_chars: int, compact_chars: int, artifact_id: str) -> str:\n    savings = 0.0\n    note = ""\n    for _ in range(3):\n        note = (\n            f"[Token Terminator: {savings}% fewer characters; "\n            f"full artifact={artifact_id}; recover with token_terminator action=artifact_get]"\n        )\n        delivered_chars = compact_chars + 2 + len(note)\n        savings = (\n            round((raw_chars - delivered_chars) / raw_chars * 100, 1)\n            if raw_chars\n            else 0.0\n        )\n    return (\n        f"[Token Terminator: {savings}% fewer characters; "\n        f"full artifact={artifact_id}; recover with token_terminator action=artifact_get]"\n    )\n',
)

# ---------------------------------------------------------------------------
# 8: terminal_snapshots belongs to store schema management, not an ad-hoc
# runtime migration.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/temporal.py",
    '        self.available = bool(self.enabled and self.store is not None)\n        if self.available:\n            self._initialize()\n\n    def _initialize(self) -> None:\n        if self.store is None:\n            self.available = False\n            return\n        try:\n            with self.store.connection(write=True) as conn:\n                conn.execute(\n                    """\n                    CREATE TABLE IF NOT EXISTS terminal_snapshots (\n                        state_key TEXT PRIMARY KEY,\n                        artifact_id TEXT NOT NULL,\n                        command TEXT NOT NULL,\n                        cwd TEXT NOT NULL,\n                        backend TEXT NOT NULL,\n                        session_scope TEXT NOT NULL DEFAULT \'\',\n                        updated_at TEXT NOT NULL\n                    )\n                    """\n                )\n        except Exception:  # noqa: BLE001 - optimization must fail open\n            self.available = False\n            self.metrics.add("temporal_errors")\n\n',
    '        self.available = bool(self.enabled and self.store is not None)\n\n',
)

# ---------------------------------------------------------------------------
# 5 + 7: one temporal semantic entry point shared by sync/async, and record
# exact token counts for native/temporal reductions when the tokenizer exists.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/enhancements.py",
    '    def transform_tool_result(\n        self, *, tool_name: str, args: dict, result: str, **kwargs: Any\n    ):\n        temporal = None\n        if self.config.mode in {"balanced", "aggressive"}:\n            temporal = self.temporal.transform(\n                tool_name=tool_name,\n                args=args,\n                result=result,\n                **kwargs,\n            )\n        if temporal is not None:\n            return temporal\n        return super().transform_tool_result(\n',
    '    def _temporal_transform(\n        self, *, tool_name: str, args: dict, result: str, **kwargs: Any\n    ) -> str | None:\n        if self.config.mode not in {"balanced", "aggressive"}:\n            return None\n        return self.temporal.transform(\n            tool_name=tool_name, args=args, result=result, **kwargs\n        )\n\n    def transform_tool_result(\n        self, *, tool_name: str, args: dict, result: str, **kwargs: Any\n    ):\n        temporal = self._temporal_transform(\n            tool_name=tool_name, args=args, result=result, **kwargs\n        )\n        if temporal is not None:\n            self._record_native(\n                session_id=str(kwargs.get("session_id") or ""),\n                turn_id=str(kwargs.get("turn_id") or ""),\n                raw_chars=len(result),\n                output_chars=len(temporal),\n                raw_text=result,\n                output_text=temporal,\n            )\n            return temporal\n        return super().transform_tool_result(\n',
)
# Token rejection means the original request is what the provider actually sees;
# record that actual full exposure instead of rolling claims back.
re_sub_once(
    "src/rtk_hermes_plus/enhancements.py",
    r'    def _rollback_exposure_claims\(.*?\n    def compile\(',
    '    def _record_actual_exposures(\n        self, *, session_id: str, request_id: str, artifact_ids: list[str]\n    ) -> None:\n        for artifact_id in artifact_ids:\n            try:\n                self.store.record_exposure(\n                    session_id=session_id,\n                    artifact_id=artifact_id,\n                    request_id=request_id,\n                    inline=True,\n                )\n            except Exception:\n                logger.debug("Token Terminator exposure accounting failed", exc_info=True)\n\n    def compile(',
    flags=re.S,
)
replace_once(
    "src/rtk_hermes_plus/enhancements.py",
    '        self._rollback_exposure_claims(\n            session_id=session_id,\n            request_id=result.request_id,\n        )\n',
    '        self._record_actual_exposures(\n            session_id=session_id,\n            request_id=result.request_id,\n            artifact_ids=result.artifact_ids,\n        )\n',
)

replace_once(
    "src/rtk_hermes_plus/async_runtime.py",
    '        self._raise_if_cancelled(cancellation)\n        compressor = self.runtime.compressor\n',
    '        self._raise_if_cancelled(cancellation)\n        temporal_transform = getattr(self.runtime, "_temporal_transform", None)\n        if callable(temporal_transform):\n            temporal = await self._run_sync(\n                temporal_transform,\n                tool_name=tool_name,\n                args=args,\n                result=result,\n                session_id=str(kwargs.get("session_id") or ""),\n                tool_call_id=str(kwargs.get("tool_call_id") or ""),\n                cancellation=cancellation,\n            )\n            if temporal is not None:\n                await self._run_sync(\n                    self.runtime._record_native,\n                    session_id=str(kwargs.get("session_id") or ""),\n                    turn_id=str(kwargs.get("turn_id") or ""),\n                    raw_chars=len(result),\n                    output_chars=len(temporal),\n                    raw_text=result,\n                    output_text=temporal,\n                    cancellation=cancellation,\n                )\n                return temporal\n        compressor = self.runtime.compressor\n',
)
replace_once(
    "src/rtk_hermes_plus/async_runtime.py",
    '                raw_chars=len(result),\n                output_chars=len(transformed),\n                cancellation=cancellation,\n',
    '                raw_chars=len(result),\n                output_chars=len(transformed),\n                raw_text=result,\n                output_text=transformed,\n                cancellation=cancellation,\n',
)

# Base runtime records the actual strings too, allowing RuntimeV05 to use its
# TokenBudgetAdapter without burdening older/base runtimes.
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    '                raw_chars=len(result),\n                output_chars=len(transformed),\n            )\n',
    '                raw_chars=len(result),\n                output_chars=len(transformed),\n                raw_text=result,\n                output_text=transformed,\n            )\n',
)
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    '        raw_chars: int,\n        output_chars: int,\n    ) -> None:\n        self._ensure_ledger_session(session_id)\n        self.ledger.record_native(\n            session_id=session_id,\n            turn_id=turn_id,\n            raw_chars=raw_chars,\n            output_chars=output_chars,\n        )\n',
    '        raw_chars: int,\n        output_chars: int,\n        raw_text: str = "",\n        output_text: str = "",\n    ) -> None:\n        self._ensure_ledger_session(session_id)\n        raw_tokens = 0\n        output_tokens = 0\n        token_measurements = 0\n        budget = getattr(self, "token_budget", None)\n        if budget is not None and raw_text and output_text:\n            raw_measurement = budget.measure_text(raw_text)\n            output_measurement = budget.measure_text(output_text)\n            if raw_measurement.available and output_measurement.available:\n                raw_tokens = int(raw_measurement.tokens or 0)\n                output_tokens = int(output_measurement.tokens or 0)\n                token_measurements = 1\n        self.ledger.record_native(\n            session_id=session_id,\n            turn_id=turn_id,\n            raw_chars=raw_chars,\n            output_chars=output_chars,\n            raw_tokens=raw_tokens,\n            output_tokens=output_tokens,\n            token_measurements=token_measurements,\n        )\n',
)

# ---------------------------------------------------------------------------
# 9: actual exposure accounting on the character gate too.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/compiler.py",
    '            if compiled_chars >= raw_chars:\n                result = CompileResult(\n',
    '            if compiled_chars >= raw_chars:\n                for artifact_id in artifact_ids:\n                    try:\n                        self.store.record_exposure(\n                            session_id=session_id,\n                            artifact_id=artifact_id,\n                            request_id=request_id,\n                            inline=True,\n                        )\n                    except Exception:\n                        logger.debug(\n                            "Token Terminator exposure accounting failed", exc_info=True\n                        )\n                result = CompileResult(\n',
)
# Remove two now-redundant compiler_enabled wrappers after the early return.
replace_once(
    "src/rtk_hermes_plus/compiler.py",
    '            if self.config.compiler_enabled:\n                grouped: dict[str, list[_EvidenceSlot]] = {}\n',
    '            grouped: dict[str, list[_EvidenceSlot]] = {}\n',
)
# Dedent the grouped block mechanically until the next phase comment.
text = read("src/rtk_hermes_plus/compiler.py")
start = text.index('            grouped: dict[str, list[_EvidenceSlot]] = {}\n')
end = text.index('            # Prove the preflight candidate', start)
block = text[start:end]
# The old body retained one extra indentation level after removing the if.
lines = block.splitlines(True)
for i in range(1, len(lines)):
    if lines[i].startswith("                "):
        lines[i] = lines[i][4:]
text = text[:start] + "".join(lines) + text[end:]
text = text.replace(
    '            if self.config.compiler_enabled and mode in {"messages", "responses"}:\n',
    '            if mode in {"messages", "responses"}:\n',
    1,
)
write("src/rtk_hermes_plus/compiler.py", text)

# ---------------------------------------------------------------------------
# 7 + 9: ledger measurement honesty, Windows URI, safer directory permissions.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    'import json\nimport secrets\n',
    'import json\nimport random\nimport secrets\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '        uri = f"file:{self.state_db_path.as_posix()}?mode=ro"\n',
    '        uri = self.state_db_path.expanduser().resolve().as_uri() + "?mode=ro"\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\n    native_compressions INTEGER NOT NULL DEFAULT 0,\n',
    '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\n    native_raw_tokens INTEGER NOT NULL DEFAULT 0,\n    native_output_tokens INTEGER NOT NULL DEFAULT 0,\n    native_token_measurements INTEGER NOT NULL DEFAULT 0,\n    native_compressions INTEGER NOT NULL DEFAULT 0,\n',
)
# Same column trio occurs in turns as well.
text = read("src/rtk_hermes_plus/ledger.py")
needle = '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\n    native_compressions INTEGER NOT NULL DEFAULT 0,\n'
if needle in text:
    text = text.replace(
        needle,
        '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\n    native_raw_tokens INTEGER NOT NULL DEFAULT 0,\n    native_output_tokens INTEGER NOT NULL DEFAULT 0,\n    native_token_measurements INTEGER NOT NULL DEFAULT 0,\n    native_compressions INTEGER NOT NULL DEFAULT 0,\n',
        1,
    )
write("src/rtk_hermes_plus/ledger.py", text)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)\n            try:\n                self.path.parent.chmod(0o700)\n            except OSError:\n                pass\n            with closing(self._connect()) as connection, connection:\n                connection.executescript(SCHEMA)\n',
    '            parent_existed = self.path.parent.exists()\n            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)\n            if not parent_existed:\n                try:\n                    self.path.parent.chmod(0o700)\n                except OSError:\n                    pass\n            with closing(self._connect()) as connection, connection:\n                connection.executescript(SCHEMA)\n                for table in ("sessions", "turns"):\n                    columns = {\n                        row[1] for row in connection.execute(f"PRAGMA table_info({table})")\n                    }\n                    for column in (\n                        "native_raw_tokens",\n                        "native_output_tokens",\n                        "native_token_measurements",\n                    ):\n                        if column not in columns:\n                            connection.execute(\n                                f"ALTER TABLE {table} ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"\n                            )\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '        raw_chars: int,\n        output_chars: int,\n    ) -> None:\n        self._record_effect(\n            session_id,\n            turn_id,\n            native_raw_chars=max(0, raw_chars),\n            native_output_chars=max(0, output_chars),\n            native_compressions=1,\n        )\n',
    '        raw_chars: int,\n        output_chars: int,\n        raw_tokens: int = 0,\n        output_tokens: int = 0,\n        token_measurements: int = 0,\n    ) -> None:\n        self._record_effect(\n            session_id,\n            turn_id,\n            native_raw_chars=max(0, raw_chars),\n            native_output_chars=max(0, output_chars),\n            native_raw_tokens=max(0, raw_tokens),\n            native_output_tokens=max(0, output_tokens),\n            native_token_measurements=max(0, token_measurements),\n            native_compressions=1,\n        )\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '            "native_output_chars",\n            "native_compressions",\n',
    '            "native_output_chars",\n            "native_raw_tokens",\n            "native_output_tokens",\n            "native_token_measurements",\n            "native_compressions",\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '        first, second = modes\n        result: dict[str, Any] = {\n',
    '        first, second = modes\n        result: dict[str, Any] = {\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '        if not self.available:\n            result["error"] = self.error or "experiment ledger disabled"\n            return result\n',
    '        if first == second:\n            result["error"] = "comparison modes must differ"\n            return result\n        if not self.available:\n            result["error"] = self.error or "experiment ledger disabled"\n            return result\n',
)
# Replace arbitrary observation zipping with prompt/model bucket aggregation and
# report every unpaired observation explicitly.
re_sub_once(
    "src/rtk_hermes_plus/ledger.py",
    r'        pairs = \[\].*?        return \{\n            "pairs": len\(pairs\),.*?\n        \}\n',
    '''        eligible_first = sum(len(group[first]) for group in buckets.values())
        eligible_second = sum(len(group[second]) for group in buckets.values())
        matched_groups = []
        paired_first = 0
        paired_second = 0
        for group in buckets.values():
            if not group[first] or not group[second]:
                continue
            paired_first += len(group[first])
            paired_second += len(group[second])
            matched_groups.append((_aggregate_rows(group[first]), _aggregate_rows(group[second])))
        token_deltas = [b["total_tokens"] - a["total_tokens"] for a, b in matched_groups]
        estimated_deltas = [
            b["estimated_cost_usd"] - a["estimated_cost_usd"]
            for a, b in matched_groups
            if a["estimated_cost_usd"] is not None
            and b["estimated_cost_usd"] is not None
        ]
        actual_deltas = [
            b["actual_cost_usd"] - a["actual_cost_usd"]
            for a, b in matched_groups
            if a["actual_cost_usd"] is not None and b["actual_cost_usd"] is not None
        ]
        equivalent_deltas = [
            b["api_equivalent_cost_usd"] - a["api_equivalent_cost_usd"]
            for a, b in matched_groups
            if a["api_equivalent_cost_usd"] is not None
            and b["api_equivalent_cost_usd"] is not None
        ]
        return {
            "pairs": len(matched_groups),
            "matched_groups": len(matched_groups),
            "eligible_first": eligible_first,
            "eligible_second": eligible_second,
            "paired_observations_first": paired_first,
            "paired_observations_second": paired_second,
            "unpaired_first": eligible_first - paired_first,
            "unpaired_second": eligible_second - paired_second,
            "direction": f"{second} minus {first}",
            "mean_total_tokens_delta": _mean(token_deltas),
            "median_total_tokens_delta": _median(token_deltas),
            "total_tokens_delta_ci95": _bootstrap_ci(token_deltas),
            "mean_estimated_cost_usd_delta": _mean(estimated_deltas),
            "median_estimated_cost_usd_delta": _median(estimated_deltas),
            "estimated_cost_usd_delta_ci95": _bootstrap_ci(estimated_deltas),
            "mean_actual_cost_usd_delta": _mean(actual_deltas),
            "median_actual_cost_usd_delta": _median(actual_deltas),
            "actual_cost_usd_delta_ci95": _bootstrap_ci(actual_deltas),
            "mean_api_equivalent_cost_usd_delta": _mean(equivalent_deltas),
            "median_api_equivalent_cost_usd_delta": _median(equivalent_deltas),
            "api_equivalent_cost_usd_delta_ci95": _bootstrap_ci(equivalent_deltas),
        }
''',
    flags=re.S,
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '    output["native_output_chars"] = _integer(row.get("native_output_chars"))\n    output["native_compressions"] = _integer(row.get("native_compressions"))\n',
    '    output["native_output_chars"] = _integer(row.get("native_output_chars"))\n    output["native_raw_tokens"] = _integer(row.get("native_raw_tokens"))\n    output["native_output_tokens"] = _integer(row.get("native_output_tokens"))\n    output["native_token_measurements"] = _integer(row.get("native_token_measurements"))\n    output["native_compressions"] = _integer(row.get("native_compressions"))\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '    saved_chars = max(0, raw_chars - output_chars)\n    return {\n        "sessions": len(rows),\n        "token_coverage": len(rows),\n',
    '    saved_chars = max(0, raw_chars - output_chars)\n    native_raw_tokens = sum(row["native_raw_tokens"] for row in rows)\n    native_output_tokens = sum(row["native_output_tokens"] for row in rows)\n    native_token_measurements = sum(row["native_token_measurements"] for row in rows)\n    measured_native_saved = max(0, native_raw_tokens - native_output_tokens)\n    fallback_native_saved = round(saved_chars / 4)\n    return {\n        "sessions": len(rows),\n        "token_coverage": sum(1 for row in rows if row["total_tokens"] > 0),\n',
)
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '        "native_saved_chars": saved_chars,\n        "native_estimated_tokens_saved": round(saved_chars / 4),\n',
    '        "native_saved_chars": saved_chars,\n        "native_raw_tokens": native_raw_tokens,\n        "native_output_tokens": native_output_tokens,\n        "native_token_measurement_coverage": native_token_measurements,\n        "native_measured_tokens_saved": measured_native_saved,\n        "native_estimated_tokens_saved": (\n            measured_native_saved if native_token_measurements else fallback_native_saved\n        ),\n        "native_token_savings_source": (\n            "exact-tokenizer" if native_token_measurements else "chars/4-fallback"\n        ),\n',
)
# Helpers for aggregated pairing and deterministic bootstrap intervals.
replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '\ndef _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:\n',
    '''
def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean_optional(field: str) -> float | None:
        values = [row[field] for row in rows if row.get(field) is not None]
        return statistics.fmean(values) if values else None

    return {
        "total_tokens": statistics.fmean(row["total_tokens"] for row in rows),
        "estimated_cost_usd": mean_optional("estimated_cost_usd"),
        "actual_cost_usd": mean_optional("actual_cost_usd"),
        "api_equivalent_cost_usd": mean_optional("api_equivalent_cost_usd"),
    }


def _bootstrap_ci(values: list[int | float], samples: int = 2000) -> dict[str, float] | None:
    if not values:
        return None
    if len(values) == 1:
        value = float(values[0])
        return {"low": value, "high": value}
    rng = random.Random(0x747)
    n = len(values)
    estimates = sorted(
        statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(samples)
    )
    low = estimates[max(0, int(samples * 0.025) - 1)]
    high = estimates[min(samples - 1, int(samples * 0.975))]
    return {"low": round(low, 8), "high": round(high, 8)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
''',
)

# ---------------------------------------------------------------------------
# 10: remove load-bearing dead global and duplicate middleware lookup.
# ---------------------------------------------------------------------------
replace_once("src/rtk_hermes_plus/plugin.py", '\n_runtime: Runtime | None = None\n\n', '\n')
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    'def register(ctx) -> None:\n    global _runtime\n    runtime = Runtime(profile_name=getattr(ctx, "profile_name", "default"))\n    _runtime = runtime\n\n',
    'def register(ctx) -> None:\n    runtime = Runtime(profile_name=getattr(ctx, "profile_name", "default"))\n    register_middleware = getattr(ctx, "register_middleware", None)\n\n',
)
text = read("src/rtk_hermes_plus/plugin.py")
# Retain only the first shared middleware lookup inserted above.
text = text.replace('            register_middleware = getattr(ctx, "register_middleware", None)\n', '', 1)
text = text.replace('    register_middleware = getattr(ctx, "register_middleware", None)\n    if (\n', '    if (\n', 1)
write("src/rtk_hermes_plus/plugin.py", text)

# ---------------------------------------------------------------------------
# Docs/process hygiene: all compaction controls, retention watermarks, RTK pin,
# explicit PATH trust boundary, version notes, and remove the literal $HOME fossil.
# ---------------------------------------------------------------------------
text = read("README.md")
text = text.replace("Token Terminator 0.5.0 supersedes 0.4.0", "Token Terminator 0.5.1 supersedes 0.5.0")
text = text.replace("immutable `v0.5.0` release tag", "immutable `v0.5.1` release tag")
text = text.replace("Token Terminator 0.5.0 now", "Token Terminator 0.5.1 now")
text = text.replace("@v0.5.0", "@v0.5.1")
rows = '| `TOKEN_TERMINATOR_VAULT_MAX_BYTES` | `536870912` | Total exact-content capacity |\n'
addition = rows + '| `TOKEN_TERMINATOR_VAULT_HIGH_WATER_PCT` | `90` | Start retention pruning before the hard capacity wall |\n| `TOKEN_TERMINATOR_VAULT_LOW_WATER_PCT` | `80` | Prune toward this target when the high-water mark is crossed |\n'
if rows in text:
    text = text.replace(rows, addition, 1)
backend_row = '| `TOKEN_TERMINATOR_BACKENDS` | `local` | Allowed terminal backends, comma-separated, or `all` |\n'
if backend_row in text:
    text = text.replace(backend_row, backend_row + '| `TOKEN_TERMINATOR_RTK_PATH` | empty | Optional explicit RTK executable path; avoids PATH-based discovery |\n', 1)
marker = '| `TOKEN_TERMINATOR_CONTEXT_LIMIT_TOKENS` | `0` | Optional model context limit; `0` disables budget reporting |\n'
compaction_rows = '| `TOKEN_TERMINATOR_CONTEXT_COMPACTION` | `true` | Enable deterministic old-turn/tool-result compaction |\n| `TOKEN_TERMINATOR_CONTEXT_MIN_VAULT_CHARS` | `4000` | Minimum old tool-result size eligible for context vaulting |\n| `TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS` | `6` | Collapse completed turns older than this window; `0` disables turn collapse |\n| `TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS` | `5` | Recent turns that must remain fully inline |\n| `TOKEN_TERMINATOR_PREVIEW_MARKER` | `false` | Prefix rewritten terminal commands with the RTK preview marker |\n'
if marker in text and "TOKEN_TERMINATOR_CONTEXT_COMPACTION" not in text:
    text = text.replace(marker, compaction_rows + marker, 1)
write("README.md", text)

security = read("SECURITY.md")
if "PATH-shadowing" not in security:
    security += '''\n## RTK executable trust boundary\n\nWhen `TOKEN_TERMINATOR_RTK_PATH` is unset, Token Terminator discovers `rtk` through the host process `PATH`. A malicious or accidentally shadowed executable named `rtk` can therefore influence command rewriting. Security-sensitive deployments should pin the expected executable with `TOKEN_TERMINATOR_RTK_PATH` and protect that file and its parent directory from untrusted writes. Token Terminator still invokes RTK with an argument array and `shell=False`; executable discovery is the separate trust boundary.\n'''
write("SECURITY.md", security)

text = read(".gitignore")
text = text.replace("$HOME/\n", "")
write(".gitignore", text)

changelog = read("CHANGELOG.md")
entry = '''## 0.5.1 - 2026-09-12

- Added capacity-managed vault retention with O(1) byte accounting, configurable high/low watermarks, protected temporal baselines, pruning telemetry, and status reporting instead of a permanent hard-wall failure.
- Enforced the context-collapse/inline-window invariant in direct config, environment loading, and the compactor itself; unified the inline-recent default at five turns.
- Added Unicode-correct case-insensitive artifact search using Python `casefold()` through a deterministic SQLite function.
- Keyed RTK rewrite caching by canonical working directory plus command and added `TOKEN_TERMINATOR_RTK_PATH` for explicit executable pinning.
- Restored temporal-delta parity in `AsyncRuntime` through the same v0.5 semantic temporal entry point used synchronously.
- Moved `terminal_snapshots` into vault schema management and protected referenced artifacts from retention pruning.
- Made provider-exposure lease accounting reflect the request actually delivered when character or tokenizer gates reject a candidate.
- Added exact native/temporal token-savings accounting when the configured tokenizer is available; retained and explicitly labelled the chars/4 fallback otherwise.
- Reworked experiment comparison to reject identical modes, aggregate by prompt-fingerprint/model group, report unpaired observations, and include deterministic 95% bootstrap intervals.
- Hardened Windows read-only SQLite URIs, stopped chmodding pre-existing parent directories, corrected recovery-note savings, removed dead/duplicated adapter code, and documented every context-compaction/retention/security control.

'''
if "## 0.5.1 - 2026-09-12" not in changelog:
    changelog = changelog.replace("# Changelog\n\n", "# Changelog\n\n" + entry, 1)
write("CHANGELOG.md", changelog)

# ---------------------------------------------------------------------------
# Tests reproducing the audit findings before/after the fix.
# ---------------------------------------------------------------------------
test_text = r'''from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from rtk_hermes_plus import AsyncRuntime, Runtime
from rtk_hermes_plus.config import Config, load_config
from rtk_hermes_plus.ledger import ExperimentLedger, HermesAccounting, _bootstrap_ci, _summary
from rtk_hermes_plus.metrics import Metrics
from rtk_hermes_plus.rewrite import Rewriter
from rtk_hermes_plus.storage import TokenTerminatorStore


def _config(tmp_path: Path, **kwargs) -> Config:
    values = {
        "mode": "balanced",
        "ledger_enabled": False,
        "ledger_path": tmp_path / "ledger.db",
        "state_db_path": tmp_path / "state.db",
        "db_path": tmp_path / "vault.db",
        "min_artifact_chars": 10,
        "native_min_chars": 1000,
        "graph_context_chars": 0,
    }
    values.update(kwargs)
    return Config(**values)


def test_context_defaults_are_identical_and_invalid_direct_pair_is_rejected(tmp_path, monkeypatch):
    assert Config().context_inline_recent_turns == 5
    for name in (
        "TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS",
        "TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert load_config().context_inline_recent_turns == 5
    with pytest.raises(ValueError):
        Config(context_inline_recent_turns=5, context_collapse_after_turns=2)
    monkeypatch.setenv("TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS", "5")
    monkeypatch.setenv("TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS", "2")
    loaded = load_config()
    assert loaded.context_collapse_after_turns == 5


def test_unicode_artifact_search_casefolds_content(tmp_path):
    store = TokenTerminatorStore(tmp_path / "unicode.db")
    store.put_artifact("Straße FEHLER Übergröße", tool_name="Prüfung")
    assert len(store.search_artifacts("übergröße")) == 1
    assert len(store.search_artifacts("ÜBERGRÖSSE")) == 1
    assert len(store.search_artifacts("prüfung")) == 1


def test_rewrite_cache_is_scoped_by_cwd(tmp_path, monkeypatch):
    config = _config(tmp_path, rtk_path=tmp_path / "rtk")
    rewriter = Rewriter(config, Metrics())
    calls: list[str] = []

    def fake_run(_argv, *, cwd, **_kwargs):
        calls.append(cwd)
        return SimpleNamespace(stdout=f"rewritten:{cwd}", returncode=0)

    monkeypatch.setattr("rtk_hermes_plus.rewrite.subprocess.run", fake_run)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    first = rewriter.rewrite("git status", cwd=a)
    again = rewriter.rewrite("git status", cwd=a)
    other = rewriter.rewrite("git status", cwd=b)
    assert first.command == again.command
    assert first.command != other.command
    assert len(calls) == 2


def test_async_runtime_gets_temporal_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS", "1")
    runtime = Runtime(_config(tmp_path))
    async_runtime = AsyncRuntime(runtime)
    args = {"command": "tree src", "cwd": str(tmp_path)}
    result = "\n".join(f"src/file_{i}.py" for i in range(300))

    first = asyncio.run(
        async_runtime.transform_tool_result(
            tool_name="terminal",
            args=args,
            result=result,
            session_id="s",
            tool_call_id="c1",
        )
    )
    second = asyncio.run(
        async_runtime.transform_tool_result(
            tool_name="terminal",
            args=args,
            result=result,
            session_id="s",
            tool_call_id="c2",
        )
    )
    assert first is None
    assert second is not None and "no output changes" in second


def test_vault_prunes_old_unprotected_artifacts_and_keeps_temporal_baseline(tmp_path):
    store = TokenTerminatorStore(
        tmp_path / "retention.db",
        max_artifact_chars=1000,
        max_vault_bytes=500,
        high_water_pct=80,
        low_water_pct=50,
    )
    a = store.put_artifact("a" * 180, tool_name="terminal")
    b = store.put_artifact("b" * 180, tool_name="process")
    with store.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO terminal_snapshots(state_key, artifact_id, command, cwd, backend, session_scope, updated_at) "
            "VALUES('state', ?, 'cmd', '.', 'local', '', 'now')",
            (a.artifact_id,),
        )
    c = store.put_artifact("c" * 180, tool_name="process")
    assert store.get_artifact(a.artifact_id).content.startswith("a")
    assert store.get_artifact(c.artifact_id).content.startswith("c")
    with pytest.raises(KeyError):
        store.get_artifact(b.artifact_id)
    usage = store.vault_usage()
    assert usage["vault_bytes"] == 360
    assert usage["vault_pruned_artifacts"] == 1


def test_terminal_snapshot_schema_exists_before_temporal_runtime(tmp_path):
    store = TokenTerminatorStore(tmp_path / "schema.db")
    with store.connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='terminal_snapshots'"
        ).fetchone()
    assert row is not None


def test_store_does_not_repermission_existing_parent(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permission semantics")
    parent = tmp_path / "existing"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)
    TokenTerminatorStore(parent / "vault.db")
    assert os.stat(parent).st_mode & 0o777 == 0o755


def test_hermes_accounting_uses_path_uri(tmp_path, monkeypatch):
    db = tmp_path / "a ?# b.db"
    db.touch()
    captured: list[str] = []

    class DummyConnection:
        row_factory = None

        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("stop")

        def close(self):
            pass

    def fake_connect(uri, **_kwargs):
        captured.append(uri)
        return DummyConnection()

    monkeypatch.setattr("rtk_hermes_plus.ledger.sqlite3.connect", fake_connect)
    HermesAccounting(db).read("session")
    assert captured and captured[0].startswith("file://")
    assert "%20" in captured[0] and "%3F" in captured[0] and "%23" in captured[0]


def test_pinned_rtk_path_wins_over_path_lookup(tmp_path, monkeypatch):
    pinned = tmp_path / "known-rtk"
    monkeypatch.setattr("rtk_hermes_plus.rewrite.shutil.which", lambda _name: "/evil/rtk")
    assert Rewriter(_config(tmp_path, rtk_path=pinned), Metrics()).rtk_path == str(pinned)


def test_measurement_summary_uses_real_native_tokens_when_present():
    row = {
        "total_tokens": 100,
        "estimated_cost_usd": None,
        "actual_cost_usd": None,
        "api_equivalent_cost_usd": None,
        "completed": 1,
        "failed": 0,
        "interrupted": 0,
        "native_raw_chars": 400,
        "native_output_chars": 100,
        "native_raw_tokens": 90,
        "native_output_tokens": 20,
        "native_token_measurements": 1,
        "native_compressions": 1,
        "rewrite_count": 0,
        "recovery_reads": 0,
    }
    summary = _summary([row])
    assert summary["native_estimated_tokens_saved"] == 70
    assert summary["native_token_savings_source"] == "exact-tokenizer"
    assert summary["token_coverage"] == 1


def test_bootstrap_interval_is_deterministic_and_compare_rejects_same_mode(tmp_path):
    assert _bootstrap_ci([1, 2, 3, 4]) == _bootstrap_ci([1, 2, 3, 4])
    ledger = ExperimentLedger(
        tmp_path / "ledger.db",
        tmp_path / "missing-state.db",
        plugin_version="test",
        enabled=True,
    )
    result = ledger.compare(("balanced", "balanced"))
    assert result["error"] == "comparison modes must differ"
'''
write("tests/test_v051_hardening.py", test_text)

# The v0.5 token-gate regression test now asserts the truthful provider
# exposure rather than the old rollback behavior.
text = read("tests/test_v05_enhancements.py")
text = text.replace(
    "def test_token_gate_rolls_back_lease_claim_when_receipt_expands_tokens(tmp_path):",
    "def test_token_gate_records_actual_exposure_when_receipt_expands_tokens(tmp_path):",
)
text = text.replace("    assert count == 0\n", "    assert count == 1\n")
write("tests/test_v05_enhancements.py", text)

print("v0.5.1 hardening patch applied")
