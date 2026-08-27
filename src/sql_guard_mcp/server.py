# sql-guard-mcp 서버 본체 — 안전 가드를 거친 읽기 전용 SQL 접근을 MCP 도구로 노출한다
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .db import QueryAborted, connect_readonly, describe_table, list_tables, run_query
from .guard import GuardConfig, GuardViolation

mcp = FastMCP(
    "sql-guard-mcp",
    instructions=(
        "안전 가드가 달린 읽기 전용 SQL 조회 서버. 모든 쿼리는 실행 전에 "
        "읽기 전용 검증·테이블 허용 목록·행 수 상한·실행 시간 상한을 통과해야 한다. "
        "먼저 sql_list_tables와 sql_describe_table로 스키마를 파악한 뒤 sql_query를 쓰라. "
        "설정: SQLGUARD_DB(파일 경로), SQLGUARD_ALLOWED_TABLES(쉼표 구분), SQLGUARD_MAX_ROWS."
    ),
)

_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "demo.db"


def _config() -> GuardConfig:
    """호출 시점 환경 변수로 가드 설정을 만든다."""
    tables = os.environ.get("SQLGUARD_ALLOWED_TABLES", "")
    return GuardConfig(
        max_rows=int(os.environ.get("SQLGUARD_MAX_ROWS", "200")),
        max_vm_steps=int(os.environ.get("SQLGUARD_MAX_VM_STEPS", "5000000")),
        allowed_tables=frozenset(t.strip() for t in tables.split(",") if t.strip()),
    )


def _conn() -> sqlite3.Connection:
    """읽기 전용 연결을 연다. 기본값은 동봉된 광고 도메인 데모 DB."""
    db_path = os.environ.get("SQLGUARD_DB") or _ensure_demo_db()
    return connect_readonly(db_path)


def _ensure_demo_db() -> Path:
    """데모 DB가 없으면 동봉 SQL로 생성한다 (최초 1회)."""
    if not _DEFAULT_DB.exists():
        sql = (_DEFAULT_DB.parent / "demo.sql").read_text(encoding="utf-8")
        conn = sqlite3.connect(_DEFAULT_DB)
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()
    return _DEFAULT_DB


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def sql_list_tables() -> dict:
    """조회 가능한 테이블 목록을 반환한다 (허용 목록 적용 후)."""
    conn = _conn()
    try:
        return {"tables": list_tables(conn, _config())}
    finally:
        conn.close()


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def sql_describe_table(
    table: Annotated[str, Field(description="스키마를 볼 테이블 이름 (sql_list_tables로 확인)")],
) -> dict:
    """테이블의 컬럼·타입·행 수를 반환한다."""
    conn = _conn()
    try:
        return describe_table(conn, table, _config())
    except GuardViolation as e:
        return {"error": str(e)}
    finally:
        conn.close()


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def sql_query(
    sql: Annotated[str, Field(description="실행할 SELECT/WITH 쿼리 (단일 문장)")],
) -> dict:
    """가드를 통과한 읽기 전용 쿼리를 실행한다.

    가드: SELECT/WITH만 허용, 금지 키워드 차단, 다중 문장 차단, 테이블 허용 목록,
    행 수 상한(초과 시 truncated=true), 실행 시간 상한(초과 시 중단 안내).
    """
    conn = _conn()
    try:
        return run_query(conn, sql, _config())
    except (GuardViolation, QueryAborted) as e:
        return {"error": str(e)}
    finally:
        conn.close()


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def sql_guard_status() -> dict:
    """현재 가드 설정(행 상한·VM 상한·허용 테이블)을 반환한다 — 디버깅·투명성용."""
    c = _config()
    return {
        "max_rows": c.max_rows,
        "max_vm_steps": c.max_vm_steps,
        "allowed_tables": sorted(c.allowed_tables) or "(전체 허용)",
        "db": os.environ.get("SQLGUARD_DB") or str(_DEFAULT_DB),
        "mode": "read-only (OS 수준 mode=ro + 쿼리 검증 이중 방어)",
    }


def main() -> None:
    """stdio 트랜스포트로 서버를 실행한다."""
    mcp.run()


if __name__ == "__main__":
    main()
