# 실행기·스키마 도구 테스트 — 임시 SQLite로 가드가 실제 실행까지 강제되는지 확인한다
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sql_guard_mcp.db import QueryAborted, connect_readonly, describe_table, list_tables, run_query
from sql_guard_mcp.guard import GuardConfig, GuardViolation

DEMO_SQL = (Path(__file__).resolve().parents[1] / "data" / "demo.sql").read_text(encoding="utf-8")


@pytest.fixture()
def db(tmp_path):
    """데모 스키마로 임시 DB를 만들고 읽기 전용 연결을 돌려준다."""
    path = tmp_path / "demo.db"
    conn = sqlite3.connect(path)
    conn.executescript(DEMO_SQL)
    conn.commit()
    conn.close()
    ro = connect_readonly(path)
    yield ro
    ro.close()


CFG = GuardConfig(max_rows=5)


def test_query_returns_rows_and_columns(db):
    """정상 SELECT가 컬럼·행·행 수를 돌려준다."""
    out = run_query(db, "SELECT name, channel FROM campaigns ORDER BY id", CFG)
    assert out["columns"] == ["name", "channel"]
    assert out["row_count"] == 5
    assert out["rows"][0][1] == "google"


def test_row_limit_truncates_and_flags(db):
    """행 상한 초과 시 잘라내고 truncated=True로 표시한다."""
    out = run_query(db, "SELECT * FROM daily_stats", GuardConfig(max_rows=3))
    assert out["row_count"] == 3
    assert out["truncated"] is True


def test_existing_limit_still_capped(db):
    """사용자가 큰 LIMIT을 써도 서버 상한이 이긴다."""
    # 쿼리에 큰 LIMIT을 써도 서버 상한이 이긴다 (서브쿼리 래핑)
    out = run_query(db, "SELECT * FROM daily_stats LIMIT 999", GuardConfig(max_rows=2))
    assert out["row_count"] == 2


def test_write_blocked_before_execution(db):
    """쓰기 문장은 실행 전에 가드가 차단한다."""
    with pytest.raises(GuardViolation):
        run_query(db, "DELETE FROM campaigns", CFG)


def test_readonly_connection_is_last_line_of_defense(db):
    """가드를 우회해도 OS 수준 읽기 전용 연결이 쓰기를 막는다."""
    # 가드를 우회해 직접 실행해도 OS 수준 mode=ro가 막는다
    with pytest.raises(sqlite3.OperationalError):
        db.execute("INSERT INTO campaigns VALUES (99, 'x', 'g', 1, 'active')")


def test_vm_step_cap_aborts_runaway_query(db):
    """폭주 쿼리는 VM 상한 워치독이 안내 메시지와 함께 중단한다."""
    # 카티전 곱 3중 조인 — VM 상한을 아주 낮게 걸면 중단돼야 한다
    heavy = (
        "SELECT COUNT(*) FROM daily_stats a, daily_stats b, daily_stats c, daily_stats d"
    )
    with pytest.raises(QueryAborted, match="상한"):
        run_query(db, heavy, GuardConfig(max_rows=10, max_vm_steps=1000))


def test_sql_error_is_actionable(db):
    """SQL 오류 메시지에 다음 행동(스키마 확인)이 안내된다."""
    with pytest.raises(GuardViolation, match="sql_describe_table"):
        run_query(db, "SELECT nope FROM campaigns", CFG)


def test_list_tables_respects_allowlist(db):
    """테이블 목록 조회에도 허용 목록이 적용된다."""
    all_tables = list_tables(db, GuardConfig())
    assert set(all_tables) == {"advertisers", "campaigns", "daily_stats"}
    only = list_tables(db, GuardConfig(allowed_tables=frozenset({"campaigns"})))
    assert only == ["campaigns"]


def test_describe_table_blocked_outside_allowlist(db):
    """허용 목록 밖 테이블은 스키마 조회도 거절된다."""
    cfg = GuardConfig(allowed_tables=frozenset({"campaigns"}))
    with pytest.raises(GuardViolation):
        describe_table(db, "advertisers", cfg)


def test_describe_table_returns_schema(db):
    """허용된 테이블은 컬럼·타입·행 수를 돌려준다."""
    out = describe_table(db, "campaigns", GuardConfig())
    names = [c["name"] for c in out["columns"]]
    assert names == ["id", "name", "channel", "daily_budget", "status"]
    assert out["row_count"] == 5
