# 가드 검증 로직 단위 테스트 — 실행기 없이 순수 검증만 확인한다
from __future__ import annotations

import pytest

from sql_guard_mcp.guard import GuardConfig, GuardViolation, apply_row_limit, validate_query

CFG = GuardConfig()
CFG_ALLOW = GuardConfig(allowed_tables=frozenset({"campaigns", "daily_stats"}))


def test_select_passes():
    assert validate_query("SELECT * FROM campaigns", CFG) == "SELECT * FROM campaigns"


def test_with_cte_passes():
    sql = "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
    assert validate_query(sql, CFG) == sql


def test_trailing_semicolon_stripped():
    assert validate_query("SELECT 1;", CFG) == "SELECT 1"


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO campaigns VALUES (9, 'x', 'g', 1, 'active')",
        "UPDATE campaigns SET status='paused'",
        "DELETE FROM campaigns",
        "DROP TABLE campaigns",
        "CREATE TABLE evil (x)",
        "PRAGMA writable_schema=1",
        "ATTACH DATABASE '/tmp/x.db' AS x",
    ],
)
def test_write_and_schema_statements_blocked(sql):
    with pytest.raises(GuardViolation):
        validate_query(sql, CFG)


def test_forbidden_keyword_inside_single_statement_blocked():
    # WITH로 시작하는 단일 문장이라도 본문에 쓰기 키워드가 섞이면 차단한다
    with pytest.raises(GuardViolation, match="금지된 키워드"):
        validate_query("WITH d AS (DELETE FROM campaigns RETURNING *) SELECT * FROM d", CFG)


def test_stacked_write_blocked_by_multistatement_guard():
    # 문장을 이어붙인 쓰기 시도는 다중 문장 가드가 먼저 잡는다 (다층 방어)
    with pytest.raises(GuardViolation):
        validate_query("SELECT 1; DELETE FROM campaigns", CFG)


def test_multiple_statements_blocked():
    with pytest.raises(GuardViolation, match="다중 문장"):
        validate_query("SELECT 1; SELECT 2", CFG)


def test_non_select_start_blocked():
    with pytest.raises(GuardViolation, match="SELECT 또는 WITH"):
        validate_query("EXPLAIN SELECT 1", CFG)


def test_empty_query_blocked():
    with pytest.raises(GuardViolation, match="빈 쿼리"):
        validate_query("   ", CFG)


def test_allowlist_blocks_other_tables():
    with pytest.raises(GuardViolation, match="advertisers"):
        validate_query("SELECT * FROM advertisers", CFG_ALLOW)


def test_allowlist_checks_join_tables():
    with pytest.raises(GuardViolation, match="advertisers"):
        validate_query(
            "SELECT * FROM campaigns c JOIN advertisers a ON a.id = c.id", CFG_ALLOW
        )


def test_allowlist_permits_listed_tables():
    sql = "SELECT c.name FROM campaigns c JOIN daily_stats d ON d.campaign_id = c.id"
    assert validate_query(sql, CFG_ALLOW) == sql


def test_row_limit_wraps_query():
    limited = apply_row_limit("SELECT * FROM campaigns", 50)
    assert limited == "SELECT * FROM (SELECT * FROM campaigns) LIMIT 50"
