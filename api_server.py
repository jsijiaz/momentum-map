#!/usr/bin/env python3
"""
Momentum Map API — persists state per session ID (x-session-id header).
Sessions allow unique shareable sub-page links.
"""
import json
import sqlite3
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "momap_data.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS session_state (
            session_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Legacy table for backward compat
    db.execute("""
        CREATE TABLE IF NOT EXISTS visitor_state (
            visitor_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    db.close()

init_db()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class StatePayload(BaseModel):
    state: Any

def get_session_id(request: Request) -> str:
    # Prefer x-session-id header, fall back to x-visitor-id for legacy
    return (request.headers.get("x-session-id") or
            request.headers.get("x-visitor-id") or
            "anonymous")

@app.get("/api/state")
def get_state(request: Request):
    sid = get_session_id(request)
    db = get_db()
    row = db.execute(
        "SELECT state_json FROM session_state WHERE session_id = ?", [sid]
    ).fetchone()
    if not row:
        # Check legacy table
        row = db.execute(
            "SELECT state_json FROM visitor_state WHERE visitor_id = ?", [sid]
        ).fetchone()
    db.close()
    if row:
        return json.loads(row["state_json"])
    return None

@app.post("/api/state")
def save_state(payload: StatePayload, request: Request):
    sid = get_session_id(request)
    state_json = json.dumps(payload.state)
    db = get_db()
    db.execute("""
        INSERT INTO session_state (session_id, state_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET
            state_json = excluded.state_json,
            updated_at = excluded.updated_at
    """, [sid, state_json])
    db.commit()
    db.close()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
