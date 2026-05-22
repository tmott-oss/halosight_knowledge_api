"""
Generate an API key for a company and store its hash in Supabase.

Usage:
    python3 generate_api_key.py --label "Sales Team"
    python3 generate_api_key.py --label "ChatGPT Connector" --slug halosight
"""

import argparse
import hashlib
import os
import secrets

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

COMPANY_SLUG = "halosight"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="Human-readable label for this key (e.g. 'Sales Team')")
    parser.add_argument("--slug", default=COMPANY_SLUG, help="Company slug (default: halosight)")
    args = parser.parse_args()

    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    # Look up company
    company = db.table("companies").select("id, name").eq("slug", args.slug).limit(1).execute()
    if not company.data:
        print(f"ERROR: no company found with slug '{args.slug}'")
        return

    company_id = company.data[0]["id"]
    company_name = company.data[0]["name"]

    # Generate key
    raw_key = "hk_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # Store hash
    db.table("api_keys").insert({
        "company_id": company_id,
        "key_hash": key_hash,
        "label": args.label,
    }).execute()

    print(f"\nAPI key created for {company_name} — {args.label}")
    print(f"\n  {raw_key}\n")
    print("Store this key somewhere safe. It will not be shown again.\n")


if __name__ == "__main__":
    main()
