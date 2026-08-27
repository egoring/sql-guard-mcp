-- 광고 캠페인 도메인 데모 데이터 — sql-guard-mcp 동작 시연용 합성 데이터
CREATE TABLE campaigns (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    channel TEXT NOT NULL,          -- google / tiktok / naver
    daily_budget INTEGER NOT NULL,  -- KRW
    status TEXT NOT NULL            -- active / paused
);

CREATE TABLE daily_stats (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    date TEXT NOT NULL,
    impressions INTEGER NOT NULL,
    clicks INTEGER NOT NULL,
    spend INTEGER NOT NULL          -- KRW
);

CREATE TABLE advertisers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    contact_email TEXT NOT NULL     -- 허용 목록 시연용: 기본 설정에서 제외 권장 대상
);

INSERT INTO campaigns VALUES
 (1, '여름 세일 검색광고', 'google', 300000, 'active'),
 (2, '신제품 런칭 영상', 'tiktok', 500000, 'active'),
 (3, '브랜드 키워드 방어', 'naver', 150000, 'active'),
 (4, '리타겟팅 배너', 'google', 200000, 'paused'),
 (5, '가을 프로모션 티저', 'tiktok', 350000, 'paused');

INSERT INTO advertisers VALUES
 (1, '알파리테일', 'ads@alpha-retail.example'),
 (2, '베타코스메틱', 'mkt@beta-cos.example');

INSERT INTO daily_stats (campaign_id, date, impressions, clicks, spend) VALUES
 (1, '2026-08-18', 120000, 3600, 290000),
 (1, '2026-08-19', 135000, 4050, 298000),
 (1, '2026-08-20', 128000, 3520, 285000),
 (2, '2026-08-18', 340000, 5100, 480000),
 (2, '2026-08-19', 355000, 5680, 495000),
 (2, '2026-08-20', 310000, 4340, 470000),
 (3, '2026-08-18', 45000, 2250, 140000),
 (3, '2026-08-19', 47000, 2350, 145000),
 (3, '2026-08-20', 44000, 2200, 138000),
 (4, '2026-08-18', 0, 0, 0),
 (5, '2026-08-18', 0, 0, 0);
