# SQLite 읽기 전용 연결과 가드 적용 실행기
from __future__ import annotations

import sqlite3
from pathlib import Path

from .guard import GuardConfig, GuardViolation, apply_row_limit, validate_query


class QueryAborted(RuntimeError):
    """실행 시간 상한(VM 명령 수) 초과로 쿼리를 중단했을 때."""


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    """SQLite 파일을 OS 수준 읽기 전용(mode=ro)으로 연다 — 가드의 최후 방어선."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"DB 파일이 없습니다: {path}. SQLGUARD_DB 환경 변수를 확인하거나 "
            "동봉된 데모 DB를 쓰려면 값을 비워 두세요."
        )
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def run_query(conn: sqlite3.Connection, sql: str, config: GuardConfig) -> dict:
    """가드 검증 -> LIMIT 강제 -> VM 상한 걸고 실행. 결과는 컬럼·행·잘림 여부."""
    clean = validate_query(sql, config)          # GuardViolation 가능
    limited = apply_row_limit(clean, config.max_rows + 1)  # +1로 잘림 감지

    steps = {"n": 0}

    def _watchdog() -> int:
        """SQLite progress handler — 0이 아닌 값을 돌려주면 실행이 중단된다."""
        steps["n"] += 1
        return 1 if steps["n"] * 1000 > config.max_vm_steps else 0

    conn.set_progress_handler(_watchdog, 1000)
    try:
        cur = conn.execute(limited)
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e).lower():
            raise QueryAborted(
                f"쿼리가 실행 상한(VM {config.max_vm_steps:,} steps)을 넘어 중단됐습니다. "
                "조건을 좁히거나 집계로 바꿔 다시 시도하세요."
            ) from e
        raise GuardViolation(f"SQL 오류: {e}. 스키마는 sql_describe_table로 확인하세요.") from e
    finally:
        conn.set_progress_handler(None, 0)

    truncated = len(rows) > config.max_rows
    rows = rows[: config.max_rows]
    columns = [d[0] for d in cur.description] if cur.description else []
    return {
        "columns": columns,
        "rows": [list(r) for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "max_rows": config.max_rows,
    }


def list_tables(conn: sqlite3.Connection, config: GuardConfig) -> list[str]:
    """조회 가능한 테이블 목록 — 허용 목록이 있으면 그 교집합만."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    if config.allowed_tables:
        allowed = {t.lower() for t in config.allowed_tables}
        names = [n for n in names if n.lower() in allowed]
    return names


def describe_table(conn: sqlite3.Connection, table: str, config: GuardConfig) -> dict:
    """테이블 스키마(컬럼·타입)와 행 수를 돌려준다. 허용 목록을 우회할 수 없다."""
    if table not in list_tables(conn, config):
        raise GuardViolation(
            f"'{table}' 테이블을 조회할 수 없습니다. 사용 가능: {list_tables(conn, config)}"
        )
    cols = conn.execute(f"PRAGMA table_info('{table}')").fetchall()  # 내부 호출 — 가드 대상 아님
    count = conn.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
    return {
        "table": table,
        "columns": [{"name": c[1], "type": c[2], "notnull": bool(c[3]), "pk": bool(c[5])} for c in cols],
        "row_count": count,
    }
