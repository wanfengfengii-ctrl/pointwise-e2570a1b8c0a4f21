import argparse
import json
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from finish.http import handle_finish_request
from paper.http import handle_paper_request
from plate.http import handle_plate_request
from plate.seed import seed_missing_drafts
from press.http import handle_imprint_request
from proof.http import handle_issue_request, handle_load_request
from workshop import BusinessError, canonical_json, not_found


_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "sql"
_MODES = {"authoring": 0x50574131, "station": 0x50575331}
_AUTHOR_ROUTES = {
    "drafts": handle_plate_request,
    "editions": handle_plate_request,
    "proofs": handle_issue_request,
}
_STATION_ROUTES = {
    "proof-loads": handle_load_request,
    "sheets": handle_paper_request,
    "observations": handle_paper_request,
    "impressions": handle_imprint_request,
    "acceptances": handle_finish_request,
}


def _connect(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def _initialize(path, mode):
    db = _connect(path)
    try:
        role = db.execute("PRAGMA application_id").fetchone()[0]
        if role not in (0, _MODES[mode]):
            raise ValueError("Database belongs to a different workshop mode.")
        script = (_SCHEMA_DIR / f"{mode}.sql").read_text(encoding="utf-8")
        db.executescript(f"BEGIN IMMEDIATE;\n{script}\nPRAGMA application_id = {_MODES[mode]};\nCOMMIT;")
        if mode == "authoring":
            seed_missing_drafts(db)
    except BaseException:
        db.close()
        raise
    return db


def open_authoring_store(path):
    return _initialize(path, "authoring")


def open_station_store(path):
    return _initialize(path, "station")


def _reject_json_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def _request_path(raw_target):
    try:
        target = urlsplit(raw_target)
        if target.scheme or target.netloc or target.query or target.fragment or not target.path.startswith("/"):
            raise ValueError("Expected a local path without a query or fragment.")
        segments = tuple(unquote(part, errors="strict") for part in target.path[1:].split("/"))
    except ValueError as exc:
        raise BusinessError("invalid_request", "Invalid request path.") from exc
    if not all(segments):
        raise not_found()
    return segments


def _route(mode, path):
    if mode == "authoring":
        if len(path) == 3 and path[0] == "editions" and path[2] == "check":
            return handle_issue_request
        handler = _AUTHOR_ROUTES.get(path[0])
    else:
        handler = _STATION_ROUTES.get(path[0])
    if handler is None:
        raise not_found()
    return handler


def _handler_class(mode, database):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _body(self):
            length = self.headers.get("Content-Length")
            if length is None or not length.isascii() or not length.isdecimal():
                raise BusinessError("invalid_request", "A valid Content-Length is required.")
            if self.headers.get_content_type() != "application/json":
                raise BusinessError("invalid_request", "Expected application/json.", 415)
            try:
                raw = self.rfile.read(int(length))
                value = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
                canonical_json(value)
            except (ValueError, OverflowError, RecursionError) as exc:
                raise BusinessError("invalid_json", "The request body is not valid JSON.") from exc
            if not isinstance(value, dict):
                raise BusinessError("invalid_request", "The request body must be a JSON object.")
            return value

        def _respond(self, status, value):
            body = canonical_json(value).encode("ascii")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _dispatch(self):
            try:
                path = _request_path(self.path)
                handler = _route(mode, path)
                payload = {} if self.command == "GET" else self._body()
                with closing(_connect(database)) as db:
                    status, data = handler(db, self.command, path, payload)
            except BusinessError as exc:
                status, data = exc.status, exc.to_data()
            self._respond(status, data)

        do_GET = _dispatch
        do_POST = _dispatch
        do_PUT = _dispatch

    return Handler


def create_server(mode, database, port=0):
    if mode not in _MODES:
        raise ValueError(f"Unknown workshop mode: {mode}")
    database = Path(database).resolve()
    opener = open_authoring_store if mode == "authoring" else open_station_store
    with closing(opener(database)):
        return ThreadingHTTPServer(("127.0.0.1", port), _handler_class(mode, database))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local print workshop HTTP service")
    parser.add_argument("mode", choices=tuple(_MODES))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    with create_server(args.mode, args.db, args.port) as server:
        print(f"{args.mode} listening at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
