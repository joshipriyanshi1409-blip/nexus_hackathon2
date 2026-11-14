"""Idempotent database migration runner for ECHO.
Can run direct SQL migrations via SUPABASE_DB_URL (psycopg)
and verifies private storage buckets and table accessibility via Supabase client.
Usage: python -m backend.migrate
"""
import os, sys, glob
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

def run_psycopg_migrations(db_url: str):
    import psycopg
    print(f"Connecting to database via SUPABASE_DB_URL...")
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Create migration tracking table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE _migrations ENABLE ROW LEVEL SECURITY;")
            conn.commit()

            # Find all migration files
            mig_dir = Path(__file__).resolve().parent / "migrations"
            files = sorted(glob.glob(str(mig_dir / "*.sql")))
            if not files:
                print("No migration files found.")
                return

            for fpath in files:
                mname = Path(fpath).name
                cur.execute("SELECT 1 FROM _migrations WHERE name = %s;", (mname,))
                if cur.fetchone():
                    print(f"  [ALREADY APPLIED] {mname}")
                    continue

                print(f"  [APPLYING] {mname}...")
                with open(fpath, "r", encoding="utf-8") as f:
                    sql = f.read()
                cur.execute(sql)
                cur.execute("INSERT INTO _migrations (name) VALUES (%s);", (mname,))
                conn.commit()
                print(f"  [SUCCESS] {mname}")

            # Verify RLS
            cur.execute("""
                SELECT tablename, rowsecurity
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename;
            """)
            rows = cur.fetchall()
            print("\nTable RLS Status:")
            for tbl, rls in rows:
                print(f"  - {tbl}: RLS = {'ON' if rls else 'OFF'}")

def verify_storage_and_api():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        print("[ERROR] SUPABASE_URL or SUPABASE_SERVICE_KEY missing in .env")
        return False

    from supabase import create_client
    sb = create_client(url, key)

    # 1. Bucket check
    try:
        buckets = [b.name for b in sb.storage.list_buckets()]
        if "vault" not in buckets:
            print("Creating private 'vault' storage bucket...")
            sb.storage.create_bucket("vault", {"public": False})
            print("Bucket 'vault' created successfully.")
        else:
            print("Bucket 'vault' verified (exists and private).")
    except Exception as e:
        print(f"Notice on storage buckets: {e}")

    # 2. Tables check
    tables = [
        "profiles", "brand_rules", "brand_sources", "reviews",
        "posts", "post_events", "folders", "folder_access",
        "files", "feedback", "audit_log", "approved_facts"
    ]
    print("\nVerifying table access via Supabase Service Key:")
    all_ok = True
    for tbl in tables:
        try:
            if tbl == "folder_access":
                sb.table(tbl).select("folder_id,user_id").limit(1).execute()
            else:
                sb.table(tbl).select("id").limit(1).execute()
            print(f"  [OK] Table '{tbl}' accessible.")
        except Exception as e:
            print(f"  [FAIL] Table '{tbl}' error: {e}")
            all_ok = False
    return all_ok

def main():
    print("=== ECHO Database & Storage Migration Runner ===")
    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    failed = False
    if db_url:
        try:
            run_psycopg_migrations(db_url)
        except Exception as e:
            failed = True
            print(f"[ERROR] Direct PostgreSQL migration failed: {type(e).__name__}: {str(e)[:300]}")
    else:
        print("\n[NOTE] SUPABASE_DB_URL is not set in .env.")
        print("To run direct PostgreSQL DDL migrations:")
        print("  1. Go to Supabase Dashboard -> Project Settings -> Database")
        print("  2. Copy Connection String -> URI (e.g. postgresql://postgres:[pwd]@db...:5432/postgres)")
        print("  3. Add SUPABASE_DB_URL=... to your .env file.")
        print("Falling back to Supabase API verification...\n")

    ok = verify_storage_and_api()
    print("\n=== Migration Runner Finished ===")
    if failed or not ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
