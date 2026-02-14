"""
SAM.gov Turso database module.

Uses Turso's /v2/pipeline HTTP API directly via requests — no SDK needed.

Requirements:
    pip install requests python-dotenv

Environment variables (in .env):
    TURSO_DATABASE_URL=libsql://your-database.turso.io
    TURSO_AUTH_TOKEN=your-auth-token
"""

import hashlib
import logging
import os
import re
from datetime import datetime

import requests as _requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level HTTP client for Turso /v2/pipeline
# ---------------------------------------------------------------------------

class TursoClient:
    """Minimal Turso client over HTTP — no WebSocket, no native SDK."""

    def __init__(self, db_url=None, auth_token=None):
        url = db_url or os.getenv("TURSO_DATABASE_URL", "")
        self.token = auth_token or os.getenv("TURSO_AUTH_TOKEN", "")
        # Convert libsql:// → https:// for the HTTP endpoint
        self.base_url = url.replace("libsql://", "https://")
        self.pipeline_url = f"{self.base_url}/v2/pipeline"

    # -- internals ----------------------------------------------------------

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _typed_value(v):
        """Wrap a Python value into a Turso typed-value dict."""
        if v is None:
            return {"type": "null"}
        if isinstance(v, bool):
            return {"type": "integer", "value": str(int(v))}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        if isinstance(v, float):
            return {"type": "float", "value": v}
        return {"type": "text", "value": str(v)}

    def _make_stmt(self, sql, params=None):
        stmt = {"sql": sql}
        if params:
            stmt["named_args"] = [
                {"name": k, "value": self._typed_value(v)}
                for k, v in params.items()
            ]
        return stmt

    @staticmethod
    def _parse_result(result):
        """Turn a pipeline result into {columns, rows}."""
        if result["type"] == "error":
            raise Exception(f"Turso error: {result['error']['message']}")
        resp = result["response"]["result"]
        columns = [c["name"] for c in resp.get("cols", [])]
        rows = []
        for row in resp.get("rows", []):
            rows.append(tuple(
                cell.get("value") if cell["type"] != "null" else None
                for cell in row
            ))
        return {"columns": columns, "rows": rows}

    # -- public -------------------------------------------------------------

    def execute(self, sql, params=None):
        """Run one statement and return {columns, rows}."""
        body = {
            "requests": [
                {"type": "execute", "stmt": self._make_stmt(sql, params)},
                {"type": "close"},
            ]
        }
        resp = _requests.post(self.pipeline_url, json=body, headers=self._headers())
        resp.raise_for_status()
        return self._parse_result(resp.json()["results"][0])

    def batch(self, statements):
        """
        Run many statements in one HTTP round-trip.

        *statements* is a list of (sql, params_or_None) tuples.
        """
        reqs = [
            {"type": "execute", "stmt": self._make_stmt(sql, params)}
            for sql, params in statements
        ]
        reqs.append({"type": "close"})

        resp = _requests.post(
            self.pipeline_url, json={"requests": reqs}, headers=self._headers()
        )
        resp.raise_for_status()

        results = resp.json()["results"]
        for i, r in enumerate(results):
            if r.get("type") == "error":
                raise Exception(
                    f"Turso batch error at stmt {i}: {r['error']['message']}"
                )
        return results

    def close(self):
        """No-op — kept for API compatibility."""
        pass


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS notices (
        notice_id    TEXT PRIMARY KEY,
        title        TEXT,
        href         TEXT,
        updated_date TEXT,
        address      TEXT,
        scraped_at   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contacts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT,
        email       TEXT,
        phone       TEXT,
        fingerprint TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_contacts (
        notice_id  TEXT REFERENCES notices(notice_id),
        contact_id INTEGER REFERENCES contacts(id),
        PRIMARY KEY (notice_id, contact_id)
    )
    """,
]


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------

def normalize_date(raw_date):
    """
    Best-effort normalisation of a date string to ISO 8601.

    The link scraper should already normalise dates, but this acts as a safety
    net so the  scraped_at < updated_date  comparison in get_stale_notices
    always compares like-for-like.
    """
    if not raw_date:
        return raw_date

    # Already ISO-ish (starts with YYYY-MM-DD)
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw_date):
        return raw_date

    formats = [
        "%b %d, %Y",   # Jan 15, 2025
        "%B %d, %Y",   # January 15, 2025
        "%m/%d/%Y",    # 01/15/2025
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw_date.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue

    logger.warning(f"normalize_date: could not parse '{raw_date}' – storing as-is")
    return raw_date


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def connect():
    """Return a TursoClient configured from .env."""
    return TursoClient()


def init_schema(client):
    """Create tables if they don't already exist."""
    client.batch([(sql.strip(), None) for sql in _SCHEMA])
    logger.info("Schema initialised.")


def contact_fingerprint(name, email, phone):
    raw = "|".join(
        (s or "").strip().lower() for s in [name, email, phone]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def upsert_notice(client, notice):
    """
    Upsert an index-scraper row.
    Expects dict with: notice_id, title, href, updated_date.
    Does NOT set scraped_at — only the detail scraper does that.
    """
    client.execute(
        """
        INSERT INTO notices (notice_id, title, href, updated_date)
        VALUES (:notice_id, :title, :href, :updated_date)
        ON CONFLICT(notice_id) DO UPDATE SET
            title        = excluded.title,
            href         = excluded.href,
            updated_date = excluded.updated_date
        """,
        {
            "notice_id":    notice["notice_id"],
            "title":        notice.get("title", ""),
            "href":         notice.get("href", ""),
            "updated_date": normalize_date(notice.get("updated_date", "")),
        },
    )


def upsert_notice_detail(client, detail):
    """
    Update a notice with detail-scraper data and link contacts.
    Expects dict with: notice_id, title, url, contacts, address.
    Each contact is {name, email, phone}.
    Sets scraped_at to mark this notice as detail-scraped.
    """
    address = "\n".join(detail.get("address", []))

    client.execute(
        """
        UPDATE notices SET
            title      = :title,
            address    = :address,
            scraped_at = :scraped_at
        WHERE notice_id = :notice_id
        """,
        {
            "title":     detail.get("title", ""),
            "address":   address,
            "scraped_at": datetime.now().isoformat(),
            "notice_id": detail["notice_id"],
        },
    )

    for contact in detail.get("contacts", []):
        fp = contact_fingerprint(
            contact.get("name"), contact.get("email"), contact.get("phone")
        )

        client.execute(
            """
            INSERT INTO contacts (name, email, phone, fingerprint)
            VALUES (:name, :email, :phone, :fp)
            ON CONFLICT(fingerprint) DO UPDATE SET
                name  = excluded.name,
                email = excluded.email,
                phone = excluded.phone
            """,
            {
                "name":  contact.get("name"),
                "email": contact.get("email"),
                "phone": contact.get("phone"),
                "fp":    fp,
            },
        )

        rs = client.execute(
            "SELECT id FROM contacts WHERE fingerprint = :fp", {"fp": fp}
        )
        if rs["rows"]:
            client.execute(
                """
                INSERT OR IGNORE INTO notice_contacts (notice_id, contact_id)
                VALUES (:nid, :cid)
                """,
                {"nid": detail["notice_id"], "cid": int(rs["rows"][0][0])},
            )


def get_stale_notices(client):
    """
    Return notices that need detail scraping:
      - scraped_at is NULL (never detail-scraped), OR
      - scraped_at < updated_date (listing changed since last detail scrape)
    """
    rs = client.execute(
        """
        SELECT notice_id, title, href, updated_date
        FROM notices
        WHERE scraped_at IS NULL OR scraped_at < updated_date
        """
    )
    return [dict(zip(rs["columns"], row)) for row in rs["rows"]]


def get_all_notices(client):
    rs = client.execute("SELECT * FROM notices")
    return [dict(zip(rs["columns"], row)) for row in rs["rows"]]


def get_contacts_for_notice(client, notice_id):
    rs = client.execute(
        """
        SELECT c.id, c.name, c.email, c.phone
        FROM contacts c
        JOIN notice_contacts nc ON c.id = nc.contact_id
        WHERE nc.notice_id = :nid
        """,
        {"nid": notice_id},
    )
    return [dict(zip(rs["columns"], row)) for row in rs["rows"]]


def get_notices_for_contact(client, contact_id):
    rs = client.execute(
        """
        SELECT n.*
        FROM notices n
        JOIN notice_contacts nc ON n.notice_id = nc.notice_id
        WHERE nc.contact_id = :cid
        """,
        {"cid": contact_id},
    )
    return [dict(zip(rs["columns"], row)) for row in rs["rows"]]