# sql-guard-mcp

[![CI](https://github.com/egoring/sql-guard-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/egoring/sql-guard-mcp/actions/workflows/ci.yml)

> English: [README.en.md](README.en.md)

**AI 에이전트를 위한 읽기 전용 SQL — 다층 안전 가드 내장 MCP 서버.**

LLM 에이전트에 DB를 그대로 열어주는 건 위험합니다. 이 서버는 SQLite를 4겹의 독립적인 가드 뒤에서 열어줍니다 — 에이전트가 할 수 있는 최악의 일이 "느리게 읽기"뿐이고, 그마저 상한에서 잘립니다.

## 가드 계층

| 계층 | 막는 것 | 방법 |
|---|---|---|
| **쿼리 검증** | 쓰기·스키마 변경·문장 이어붙이기 | 단일 `SELECT`/`WITH`만 허용, 금지 키워드 스캔(`INSERT`·`DROP`·`PRAGMA`·`ATTACH`…), 다중 문장 차단 |
| **테이블 허용 목록** | 민감 테이블(PII 등) 접근 | `FROM`/`JOIN` 식별자를 `SQLGUARD_ALLOWED_TABLES`와 대조, 목록·스키마 조회에도 적용 |
| **행 수 상한** | 컨텍스트 윈도 범람 | 모든 쿼리를 서브쿼리로 감싸 서버측 `LIMIT` 강제 — 사용자 `LIMIT 999999`로 우회 불가, 잘림은 `truncated`로 표시 |
| **실행 상한** | 폭주 쿼리(카티전 조인) | SQLite progress handler 워치독이 VM 명령 수 초과 시 중단 + 대처법 안내 |
| **OS 수준 읽기 전용** | 위 전부가 뚫려도 | `mode=ro` 연결 — SQLite가 강제하는 최후 방어선 |

설계 원칙은 실서비스 LLM 에이전트의 결정 가드를 만들며 얻은 것입니다. **모델이 조심하길 기대하지 말고, 부주의가 불가능하게 만들 것. 그리고 모든 거절 메시지는 에이전트에게 다음 행동을 알려줄 것.**

## 도구

`sql_list_tables` · `sql_describe_table` · `sql_query` · `sql_guard_status`(현재 가드 설정 조회)

## 데모

Claude Desktop에 연결해 동봉된 광고 캠페인 데모 DB를 조회하고 — 삭제 요청은 거절하는 장면:

![sql-guard-mcp 데모: CTR 순위 응답, DELETE 요청 거절](docs/demo.png)

에이전트는 자유롭게 탐색·집계하지만("CTR이 가장 좋은 활성 캠페인은?"), `campaigns` 테이블을 지우라고 하면 가드가 거절하고 에이전트가 이유를 설명합니다 — 프롬프트가 아니라 코드가 강제하는 읽기 전용입니다.

## 설치

MCP SDK 외 의존성 없음 — 광고 캠페인 합성 데모 DB가 동봉되어 첫 실행 시 자동 생성됩니다.

```bash
pip install -e .

export SQLGUARD_DB="/path/to/your.db"                   # 기본: 동봉 데모
export SQLGUARD_ALLOWED_TABLES="campaigns,daily_stats"  # 기본: 전체 허용
export SQLGUARD_MAX_ROWS="200"
```

Claude Desktop 설정은 [examples/](examples/claude_desktop_config.json) 참조. 설정 후 "지난주 CTR이 가장 좋았던 활성 캠페인은?"처럼 물으면 에이전트가 가드 안에서 스키마를 탐색하고 조회합니다. 삭제를 시켜보세요 — 거절 메시지를 읽어보시면 됩니다.

## 테스트

```bash
pip install -e ".[dev]"
pytest   # 29건 — 적대적 케이스 포함 (문장 이어붙이기, WITH 안의 DELETE, JOIN 허용 목록 우회, LIMIT 덮어쓰기, 폭주 조인 중단)
```

## 라이선스

MIT
