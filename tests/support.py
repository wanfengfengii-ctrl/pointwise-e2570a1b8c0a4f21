import argparse
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from press.runtime import create_server


class LocalSite:
    def __init__(self, mode, database):
        self.server = create_server(mode, database)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("HTTP service did not stop.")

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            response = build_opener(ProxyHandler({})).open(req, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            return response.code, json.load(response)

    def call(self, method, path, payload=None, status=200):
        observed, body = self.request(method, path, payload)
        if observed != status:
            raise AssertionError(f"{method} {path}: expected {status}, got {observed} {body}")
        return body


class Rig:
    def __enter__(self):
        self.temp = TemporaryDirectory(prefix="print-workshop-")
        self.root = Path(self.temp.name)
        self.author_db = self.root / "authoring.sqlite"
        self.station_db = self.root / "station.sqlite"
        self.author = self.station = None
        try:
            self.start_author()
            self.start_station()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.stop_author()
        finally:
            try:
                self.stop_station()
            finally:
                self.temp.cleanup()

    def start_author(self):
        self.author = LocalSite("authoring", self.author_db)

    def start_station(self):
        self.station = LocalSite("station", self.station_db)

    def stop_author(self):
        if self.author is not None:
            self.author.stop()
            self.author = None

    def stop_station(self):
        if self.station is not None:
            self.station.stop()
            self.station = None

    def freeze(self, source, status=201):
        return self.author.call("POST", "/editions", source, status)

    def preview(self, edition_id):
        return self.author.call("GET", f"/editions/{edition_id}/check")

    def issue(self, edition_id, status=201):
        return self.author.call("POST", "/proofs", {"edition_id": edition_id}, status)

    def load(self, artifact, status=201, **overrides):
        body = artifact["body"]
        payload = {"proof_id": body["proof_id"], "edition_id": body["edition_id"], "artifact": artifact}
        payload.update(overrides)
        return self.station.call("POST", "/proof-loads", payload, status)

    def install(self, source):
        edition = self.freeze(source)
        artifact = self.issue(edition["edition_id"])
        self.load(artifact)
        return artifact

    def register(self, sheet_id, proof_id, status=201):
        return self.station.call("POST", "/sheets", {"sheet_id": sheet_id, "proof_id": proof_id}, status)

    def paper(self, sheet_id):
        return self.station.call("GET", f"/sheets/{sheet_id}")

    def observe(self, sheet_id, point, *, probe="edge", status=201):
        return self.station.call("POST", "/observations", {"sheet_id": sheet_id, "probe": probe, "point": point}, status)

    def imprint(self, sheet_id, face, command="P", status=201):
        payload = {"sheet_id": sheet_id, "face": face, "command": command}
        return self.station.call("POST", "/impressions", payload, status)

    def impressions(self, sheet_id):
        return self.station.call("GET", f"/impressions/{sheet_id}")["impressions"]

    def inspect(self, sheet_ids, status=201):
        return self.station.call("POST", "/acceptances", {"sheet_ids": sheet_ids}, status)

    def receipt(self, acceptance_id, status=200):
        return self.station.call("GET", f"/acceptances/{acceptance_id}", status=status)


class WorkshopCase(unittest.TestCase):
    def setUp(self):
        self.rig = self.enterContext(Rig())

    def direct_proof(self, front, back=None):
        return self.rig.install({"spec": plate(front, back)})["body"]["proof_id"]

    def assert_error(self, response, code):
        self.assertEqual(response.get("error"), code, response)


def plate(front, back=None):
    faces = {"front": [list(point) for point in front]}
    if back is not None:
        faces["back"] = [list(point) for point in back]
    return {"width": 5, "height": 3, "sides": "single" if back is None else "double", "faces": faces}


def count(database, table):
    if table not in {"drafts", "editions", "issued_proofs", "acceptances"}:
        raise ValueError(table)
    with closing(sqlite3.connect(database)) as db:
        return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def scenario(case_id, input_data, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    if expected != actual or downstream_expected != downstream_actual:
        raise AssertionError(f"Scenario evidence differs from its oracle: {case_id}")
    value = {
        "case_id": case_id,
        "input": input_data,
        "expected": expected,
        "actual": actual,
        "downstream_expected": downstream_expected,
        "downstream_actual": downstream_actual,
        "code_paths": code_paths,
        "oracle": oracle,
    }
    print("POINTWISE_SCENARIO " + json.dumps(value, ensure_ascii=True, sort_keys=True), flush=True)


def demo():
    sample = Path(__file__).resolve().parents[1] / "examples" / "workday.json"
    workday = json.loads(sample.read_text(encoding="utf-8"))
    with Rig() as rig:
        draft_ids = sorted({row["draft_id"] for row in workday["sheets"]})
        proofs = {}
        previews = {}
        for draft_id in draft_ids:
            edition = rig.freeze({"draft_id": draft_id})
            previews[draft_id] = rig.preview(edition["edition_id"])["by_direction"]
            artifact = rig.issue(edition["edition_id"])
            rig.load(artifact)
            proofs[draft_id] = artifact["body"]["proof_id"]
        expected_previews = {
            "community-common": {"left": ["P"], "right": ["P"]},
            "community-split": {"left": ["P"], "right": ["Q"]},
            "community-single": {},
        }
        if previews != expected_previews:
            raise AssertionError(previews)
        rig.stop_author()
        for row in workday["sheets"]:
            rig.register(row["sheet_id"], proofs[row["draft_id"]])
            rig.imprint(row["sheet_id"], "front")
        common = rig.imprint("CENTER", "back")
        pending = rig.imprint("EAST", "back", status=409)
        east = workday["east_observation"]
        rig.observe("EAST", east["point"], probe=east["probe"])
        rejected = rig.imprint("EAST", "back", "Q", status=409)
        repaired = rig.imprint("EAST", "back")
        first = rig.inspect([row["sheet_id"] for row in workday["sheets"]])
        observed = (common["position"], pending["error"], rejected["error"], repaired["position"],
                    [row["sheet_id"] for row in first["completed"]], [row["sheet_id"] for row in first["unfinished"]])
        if observed != ([[2, 1]], "needs_orientation", "incompatible", [[1, 1]], ["CARD", "CENTER", "EAST"], ["WEST"]):
            raise AssertionError(observed)
        west = workday["west_observation"]
        rig.observe("WEST", west["point"], probe=west["probe"])
        final_back = rig.imprint("WEST", "back", "Q")
        rig.stop_station()
        rig.start_station()
        retrieved = rig.receipt(first["acceptance_id"])
        second = rig.inspect(["WEST"])
        if retrieved != first or final_back["position"] != [[1, 1]] or second["completed_count"] != 1:
            raise AssertionError((retrieved, final_back, second))
        print(json.dumps({
            "nominal_commands": previews,
            "common_back": common,
            "first_east_request": pending,
            "invalid_east_command": rejected,
            "retrieved_first_acceptance": retrieved,
            "west_acceptance_after_printing": second,
        }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the workshop sample over loopback HTTP")
    parser.add_argument("command", choices=("demo",))
    parser.parse_args()
    demo()
