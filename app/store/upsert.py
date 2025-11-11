import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---
HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parents[2]
DB_PATH = PROJECT_ROOT / "data" / "companies.db"
SCHEMA_PATH = PROJECT_ROOT / "app" / "store" / "schema.sql"

# Make sure the data directory exists so the DB file can be created
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection using row factory defaults."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Ensure the SQLite database exists and apply lightweight migrations."""
    if DB_PATH.exists():
        conn = get_connection()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(funded_companies)")}
        except sqlite3.OperationalError:
            conn.close()
        else:
            migrations_applied = False
            if "linkedin_url" not in columns:
                print("🔧 Migrating DB: adding linkedin_url column...")
                conn.execute("ALTER TABLE funded_companies ADD COLUMN linkedin_url TEXT")
                migrations_applied = True
            if "tech_roles" not in columns:
                print("🔧 Migrating DB: adding tech_roles column...")
                conn.execute("ALTER TABLE funded_companies ADD COLUMN tech_roles INTEGER DEFAULT 0")
                migrations_applied = True
            if migrations_applied:
                conn.commit()
                print("✅ Schema migration applied.")
            conn.close()
            return
        # If we reach here, the DB exists but table is missing/corrupt -> rebuild below.

    print(f"🗃️  Initialising database at {DB_PATH}...")

    try:
        schema = SCHEMA_PATH.read_text()
        conn = get_connection()
        conn.executescript(schema)
        conn.commit()
        conn.close()
        print("✅ Database schema ensured.")
    except Exception as exc:
        print(f"❌ Database initialization failed: {exc}")
        if DB_PATH.exists():
            DB_PATH.unlink(missing_ok=True)
        raise


def check_articles_exist(article_urls: list[str]) -> set[str]:
    """
    Given a list of article/source URLs, return the subset already stored.
    """
    if not article_urls:
        return set()

    conn = get_connection()
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(article_urls))
    query = (
        f"SELECT source_url FROM funded_companies "
        f"WHERE source_url IN ({placeholders})"
    )

    try:
        cur.execute(query, article_urls)
        return {row[0] for row in cur.fetchall()}
    except Exception as exc:
        print(f"❌ DB Check Error: {exc}")
        return set()
    finally:
        conn.close()


def upsert_company(data: dict) -> None:
    """Insert or update a company's funding + hiring snapshot."""
    conn = get_connection()
    cur = conn.cursor()

    announcement_date = (data.get("published_at") or "").split("T")[0] or None
    investors_json = json.dumps(data.get("investors", []))

    sql = """
    INSERT INTO funded_companies (
        company_name,
        website_url,
        linkedin_url,
        amount_raised_usd,
        funding_round,
        investors,
        lead_investor,
        headquarter_country,
        announcement_date,
        hiring_tier,
        tech_roles,
        careers_url,
        ats_provider,
        source_url,
        last_seen
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(company_name, funding_round, announcement_date)
    DO UPDATE SET
        amount_raised_usd = COALESCE(excluded.amount_raised_usd, amount_raised_usd),
        website_url      = COALESCE(excluded.website_url,      website_url),
        linkedin_url     = COALESCE(excluded.linkedin_url,     linkedin_url),
        investors        = excluded.investors,
        lead_investor    = COALESCE(excluded.lead_investor,    lead_investor),
        hiring_tier      = excluded.hiring_tier,
        tech_roles       = COALESCE(excluded.tech_roles,       tech_roles),
        careers_url      = excluded.careers_url,
        ats_provider     = excluded.ats_provider,
        last_seen        = excluded.last_seen;
    """

    tech_roles_value = data.get("tech_roles")
    if tech_roles_value is None:
        tech_roles_value = 0

    params = (
        data.get("company_name"),
        data.get("domain") or data.get("website_url"),
        data.get("linkedin_url"),
        data.get("amount_raised_usd"),
        data.get("funding_round"),
        investors_json,
        data.get("lead_investor"),
        data.get("headquarter_country"),
        announcement_date,
        data.get("hiring_tier"),
        tech_roles_value,
        data.get("careers_url"),
        data.get("ats_provider"),
        data.get("source_url") or data.get("url"),
        datetime.now(timezone.utc).isoformat(),
    )

    try:
        cur.execute(sql, params)
        conn.commit()
        print(f"📝 Upserted {data.get('company_name')} (rowcount={cur.rowcount})")
    except Exception as exc:
        print(f"❌ DB Upsert Error ({data.get('company_name')}): {exc}")
        print("   params:", params)
    finally:
        conn.close()


__all__ = [
    "get_connection",
    "init_db",
    "upsert_company",
    "check_articles_exist",
    "DB_PATH",
]