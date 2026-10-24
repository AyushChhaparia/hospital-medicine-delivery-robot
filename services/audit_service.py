from models import db, AuditLog


def log_audit(action, entity_type, entity_id=None, details=None, user_id=None):
    """
    Record an action into the audit_logs table.
    """
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
        )
        db.session.add(log_entry)
        db.session.commit()
        return log_entry
    except Exception as e:
        db.session.rollback()
        # Non-fatal to prevent breaking main business flow if logging fails
        print(f"[AUDIT LOG ERROR] Failed to record audit log: {e}")
        return None
