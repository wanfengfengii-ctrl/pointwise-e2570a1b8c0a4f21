import json
import re
from contextlib import contextmanager


class BusinessError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status

    def to_data(self):
        return {"error": self.code, "message": str(self)}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fields(value, *names, code="invalid_request", status=400):
    if not isinstance(value, dict) or value.keys() != set(names):
        expected = ", ".join(sorted(names))
        raise BusinessError(code, f"Expected exactly these fields: {expected}.", status)
    return value


def identifier(value, name):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value) is None:
        raise BusinessError("invalid_request", f"Invalid {name}.")
    return value


def not_found():
    return BusinessError("route_not_found", "This route is unavailable in the current mode.", 404)


@contextmanager
def transaction(db, *, write=False):
    db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        yield
        db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
