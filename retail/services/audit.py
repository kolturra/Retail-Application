from retail import clock


def log(conn, action, entity, entity_id=None, detail="", actor="owner"):
    """Append an audit row. Runs inside the caller's transaction."""
    conn.execute(
        "INSERT INTO audit_log(at, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
        (clock.now_iso(), actor, action, entity, entity_id, detail),
    )
