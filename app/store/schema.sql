CREATE TABLE IF NOT EXISTS funded_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core company & funding data
    company_name TEXT NOT NULL,
    website_url TEXT,
    linkedin_url TEXT,
    amount_raised_usd INTEGER,
    funding_round TEXT,
    investors TEXT,
    lead_investor TEXT,
    headquarter_country TEXT,
    announcement_date TEXT,

    -- Hiring signal enrichment
    hiring_tier TEXT,
    tech_roles INTEGER DEFAULT 0,
    careers_url TEXT,
    ats_provider TEXT,

    -- Provenance + tracking
    source_url TEXT,
    last_seen TEXT,

    -- Unique constraint ensures one record per company/funding event
    UNIQUE(company_name, funding_round, announcement_date)
);

CREATE INDEX IF NOT EXISTS idx_hiring_tier
    ON funded_companies (hiring_tier);

CREATE INDEX IF NOT EXISTS idx_last_seen
    ON funded_companies (last_seen);