import hashlib
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_db

bearer = HTTPBearer()


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_api_key(credentials: HTTPAuthorizationCredentials = Security(bearer)) -> dict:
    """
    Validate the Bearer token and return {"company_id": "...", "label": "..."}.
    Raises 401 if the key is missing or invalid.
    """
    key_hash = _hash_key(credentials.credentials)
    db = get_db()

    result = (
        db.table("api_keys")
        .select("company_id, label")
        .eq("key_hash", key_hash)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return result.data[0]
