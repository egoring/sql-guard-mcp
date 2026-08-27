# SQL 안전 가드 — 에이전트가 보낸 쿼리를 실행 전에 검증·제한하는 순수 로직
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 읽기 전용을 깨뜨릴 수 있는 키워드 — 첫 토큰이 아니어도 전체에서 차단
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|reindex|grant|revoke)\b",
    re.I,
)
# 허용되는 시작 토큰 — SELECT 또는 WITH(CTE)만
_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.I)
# FROM/JOIN 뒤의 테이블 식별자 추출 (서브쿼리·따옴표 제외한 보수적 매칭)
_TABLE_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.I)
# 문장 끝 세미콜론 하나는 허용, 그 외 세미콜론은 다중 문장으로 간주
_MULTI_STMT_RE = re.compile(r";\s*\S")


class GuardViolation(ValueError):
    """가드 위반 — 이유와 해결 방법을 담은 메시지로 에이전트를 안내한다."""


@dataclass(frozen=True)
class GuardConfig:
    """가드 동작 설정. 환경 변수로 덮어쓸 수 있다 (server.py 참조)."""

    max_rows: int = 200               # 결과 행 수 상한
    max_vm_steps: int = 5_000_000     # SQLite VM 명령 수 상한 (실행 시간 상한 역할)
    allowed_tables: frozenset[str] = field(default_factory=frozenset)  # 비어 있으면 전체 허용


def validate_query(sql: str, config: GuardConfig) -> str:
    """쿼리를 검증하고 정리된 SQL을 돌려준다. 위반 시 GuardViolation."""
    stripped = sql.strip()
    if not stripped:
        raise GuardViolation("빈 쿼리입니다. SELECT 문을 보내세요.")

    if _MULTI_STMT_RE.search(stripped):
        raise GuardViolation(
            "다중 문장은 허용되지 않습니다. 세미콜론으로 이어붙이지 말고 SELECT 하나만 보내세요."
        )

    if not _ALLOWED_START.match(stripped):
        raise GuardViolation(
            "SELECT 또는 WITH로 시작하는 읽기 쿼리만 허용됩니다. "
            "쓰기·스키마 변경은 이 서버의 범위 밖입니다."
        )

    forbidden = _FORBIDDEN.search(stripped)
    if forbidden:
        raise GuardViolation(
            f"금지된 키워드 '{forbidden.group(0)}'가 포함돼 있습니다. "
            "이 서버는 읽기 전용입니다 — 데이터 변경·스키마 조작은 할 수 없습니다."
        )

    if config.allowed_tables:
        referenced = {t.lower() for t in _TABLE_RE.findall(stripped)}
        blocked = referenced - {t.lower() for t in config.allowed_tables}
        if blocked:
            raise GuardViolation(
                f"허용 목록에 없는 테이블입니다: {sorted(blocked)}. "
                f"사용 가능한 테이블: {sorted(config.allowed_tables)} (sql_list_tables로 확인)."
            )

    return stripped.rstrip(";").strip()


def apply_row_limit(sql: str, max_rows: int) -> str:
    """행 수 상한을 강제한다 — 원 쿼리를 서브쿼리로 감싸 LIMIT을 항상 적용."""
    return f"SELECT * FROM ({sql}) LIMIT {int(max_rows)}"
