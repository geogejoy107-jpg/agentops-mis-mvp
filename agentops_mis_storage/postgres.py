"""Optional Postgres adapter primitives for AgentOps MIS.

This module must remain importable without psycopg installed. The default Free
Local runtime is still SQLite; Postgres is an opt-in BYOC/commercial path.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class PostgresAdapterUnavailable(RuntimeError):
    """Raised when the optional Postgres driver is not installed."""


@dataclass(frozen=True)
class PostgresConnectionConfig:
    dsn: str


def connection_config_from_env(prefix: str = "AGENTOPS_POSTGRES") -> PostgresConnectionConfig | None:
    dsn = os.environ.get(f"{prefix}_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    return PostgresConnectionConfig(dsn=dsn)


def load_psycopg():
    try:
        import psycopg  # type: ignore
    except ModuleNotFoundError as exc:
        raise PostgresAdapterUnavailable(
            "Optional Postgres support requires psycopg. Install psycopg in the BYOC/Enterprise runtime; "
            "Free Local does not require it."
        ) from exc
    return psycopg


def _scan_placeholders(sql: str, *, named: bool) -> tuple[str, list[str] | int]:
    output: list[str] = []
    names: list[str] = []
    positional_count = 0
    in_single = False
    i = 0
    while i < len(sql):
        char = sql[i]
        if char == "'":
            output.append(char)
            if i + 1 < len(sql) and sql[i + 1] == "'":
                output.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if named and char == ":" and not in_single:
            match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[i:])
            if match:
                name = match.group(1)
                output.append(f"%({name})s")
                names.append(name)
                i += len(name) + 1
                continue
        if not named and char == "?" and not in_single:
            output.append("%s")
            positional_count += 1
            i += 1
            continue
        output.append(char)
        i += 1
    return "".join(output), names if named else positional_count


def translate_named_sql(sql: str) -> tuple[str, list[str]]:
    translated, names = _scan_placeholders(sql, named=True)
    return translated, list(names)


def translate_qmark_sql(sql: str) -> tuple[str, int]:
    translated, count = _scan_placeholders(sql, named=False)
    return translated, int(count)


def translate_sql(sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> tuple[str, Any]:
    if params is None:
        return sql, None
    if isinstance(params, Mapping):
        translated, names = translate_named_sql(sql)
        missing = [name for name in names if name not in params]
        if missing:
            raise KeyError(f"Missing named SQL params: {missing}")
        return translated, dict(params)
    if isinstance(params, (str, bytes, bytearray)):
        raise TypeError("Postgres positional SQL params must be a non-string sequence.")
    translated, count = translate_qmark_sql(sql)
    values = list(params)
    if len(values) != count:
        raise ValueError(f"Expected {count} positional SQL params, got {len(values)}.")
    return translated, values


def split_sql_script(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    dollar_quote: str | None = None
    i = 0
    while i < len(sql):
        if dollar_quote:
            if sql.startswith(dollar_quote, i):
                current.append(dollar_quote)
                i += len(dollar_quote)
                dollar_quote = None
                continue
            current.append(sql[i])
            i += 1
            continue
        if sql[i] == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if match:
                dollar_quote = match.group(0)
                current.append(dollar_quote)
                i += len(dollar_quote)
                continue
        char = sql[i]
        if char == "'":
            current.append(char)
            if i + 1 < len(sql) and sql[i + 1] == "'":
                current.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if char == ";" and not in_single:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


class PostgresAdapter:
    """Small psycopg-backed execution wrapper with SQLite-style SQL translation."""

    def __init__(self, connection):
        self.connection = connection

    @classmethod
    def connect(cls, dsn: str):
        psycopg = load_psycopg()
        try:
            from psycopg.rows import dict_row  # type: ignore
        except Exception:
            dict_row = None
        kwargs = {"row_factory": dict_row} if dict_row is not None else {}
        return cls(psycopg.connect(dsn, **kwargs))

    def close(self) -> None:
        self.connection.close()

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def execute(self, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None):
        translated, translated_params = translate_sql(sql, params)
        return self.connection.execute(translated, translated_params)

    def executescript(self, sql: str) -> None:
        for statement in split_sql_script(sql):
            self.connection.execute(statement)

    def fetchone(self, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> dict[str, Any] | None:
        row = self.execute(sql, params).fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        return dict(row)

    def fetchall(self, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> list[dict[str, Any]]:
        rows = self.execute(sql, params).fetchall()
        return [row if isinstance(row, dict) else dict(row) for row in rows]
