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

    def repair_order(self, sheet_id, impression_id, readings, status=201):
        payload = {"sheet_id": sheet_id, "impression_id": impression_id, "readings": readings}
        return self.station.call("POST", "/repair-orders", payload, status)

    def repair_order_detail(self, order_id, status=200):
        return self.station.call("GET", f"/repair-orders/{order_id}", status=status)

    def repair_execution(self, order_id, action_no, status=201):
        payload = {"order_id": order_id, "action_no": action_no}
        return self.station.call("POST", "/repair-executions", payload, status)

    def repair_print(self, repair_id, status=200):
        return self.station.call("GET", f"/repair-executions/{repair_id}", status=status)


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
    if table not in {"drafts", "editions", "issued_proofs", "acceptances",
                     "repair_orders", "repair_prints"}:
        raise ValueError(table)
    with closing(sqlite3.connect(database)) as db:
        return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def install_repair_proof(rig, spec, repair):
    edition = rig.freeze({"spec": spec})
    artifact = rig.author.call("POST", "/proofs",
                               {"edition_id": edition["edition_id"], "repair": repair}, 201)
    rig.load(artifact)
    return artifact


def greedy_repair_cover(demand, candidates):
    """Max-coverage-first greedy exact cover; returns chosen action numbers or None when stuck."""
    remaining = set(demand)
    chosen = []
    while remaining:
        options = [(action_no, set(cells)) for action_no, cells in candidates if set(cells) <= remaining]
        if not options:
            return None
        action_no, cover = max(options, key=lambda item: (len(item[1]), -item[0]))
        chosen.append(action_no)
        remaining -= cover
    return chosen


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


def repair_demo(rig):
    if rig.author is None:
        rig.start_author()
    summary = {}

    # 场景一：最大覆盖首选导致剩格无解。动作 1 覆盖三格是贪心首选，
    # 但留下 (3,0) 无可再补；最优组是动作 2 与 3。
    greedy_proof = install_repair_proof(rig, plate([(0, 0), (1, 0), (2, 0), (3, 0)]), {
        "repairable": [[0, 0], [1, 0], [2, 0], [3, 0]],
        "forbidden": [],
        "plates": [
            {"position": [1, 0], "cells": [[0, 0], [1, 0], [2, 0]]},
            {"position": [0, 0], "cells": [[0, 0], [1, 0]]},
            {"position": [2, 0], "cells": [[2, 0], [3, 0]]},
        ],
    })["body"]["proof_id"]
    rig.register("GREEDY", greedy_proof)
    greedy_front = rig.imprint("GREEDY", "front")
    rig.observe("GREEDY", [0, 0])
    greedy_order = rig.repair_order("GREEDY", greedy_front["impression_id"],
                                    [[0, 0], [1, 0], [2, 0], [3, 0]])
    greedy_plan = [action["action_no"] for action in greedy_order["actions"]]
    greedy_attempt = greedy_repair_cover({(0, 0), (1, 0), (2, 0), (3, 0)}, [
        (1, {(0, 0), (1, 0), (2, 0)}), (2, {(0, 0), (1, 0)}), (3, {(2, 0), (3, 0)})])
    if greedy_plan != [2, 3] or greedy_attempt is not None:
        raise AssertionError(("greedy", greedy_plan, greedy_attempt))
    summary["greedy_trap"] = {
        "greedy_first_choice": {"action_no": 1, "covers": 3, "remaining_solvable": False},
        "issued_plan": greedy_plan,
        "order": greedy_order,
    }

    # 场景二：各可能纸向各有解但没有共同动作组。动作 1 在右向会碰禁止格，
    # 动作 2 在左向会碰禁止格；两向各自可解，共同组无解。
    split_proof = install_repair_proof(rig, plate([(2, 1)]), {
        "repairable": [[2, 1], [4, 1]],
        "forbidden": [[0, 1]],
        "plates": [
            {"position": [2, 1], "cells": [[2, 1], [4, 1]]},
            {"position": [2, 1], "cells": [[0, 1], [2, 1]]},
        ],
    })["body"]["proof_id"]
    rig.register("SPLIT", split_proof)
    split_front = rig.imprint("SPLIT", "front")
    blocked = rig.repair_order("SPLIT", split_front["impression_id"], [[2, 1]])
    rig.observe("SPLIT", [0, 0])
    left_order = rig.repair_order("SPLIT", split_front["impression_id"], [[2, 1]])
    rig.register("SPLIT-R", split_proof)
    split_r_front = rig.imprint("SPLIT-R", "front")
    rig.observe("SPLIT-R", [4, 0])
    right_order = rig.repair_order("SPLIT-R", split_r_front["impression_id"], [[2, 1]])
    rig.register("SPLIT-X", split_proof)
    split_x_front = rig.imprint("SPLIT-X", "front")
    stuck = rig.repair_order("SPLIT-X", split_x_front["impression_id"], [[2, 1]])
    per_direction = ([action["action_no"] for action in left_order["actions"]],
                     [action["action_no"] for action in right_order["actions"]])
    if not (blocked["status"] == stuck["status"] == "unsolvable" and per_direction == ([1], [2])):
        raise AssertionError(("split", blocked["status"], stuck["status"], per_direction))
    summary["no_common_action_set"] = {
        "both_directions": blocked["status"],
        "left_only_plan": per_direction[0],
        "right_only_plan": per_direction[1],
        "unsolvable_order": stuck,
    }

    # 场景三：实做一半后补测换单。首单两向可行，实做动作 1 后补测缩小纸向，
    # 旧单迟到命令被拒，新单扣除已实做覆盖后只补剩余格。
    half_proof = install_repair_proof(rig, plate([(1, 1), (3, 1)]), {
        "repairable": [[1, 1], [3, 1]],
        "forbidden": [],
        "plates": [
            {"position": [1, 1], "cells": [[1, 1]]},
            {"position": [3, 1], "cells": [[3, 1]]},
        ],
    })["body"]["proof_id"]
    rig.register("HALF", half_proof)
    half_front = rig.imprint("HALF", "front")
    first_order = rig.repair_order("HALF", half_front["impression_id"], [[1, 1], [3, 1]])
    first_hit = rig.repair_execution(first_order["order_id"], 1)
    rig.observe("HALF", [0, 0])
    late = rig.repair_execution(first_order["order_id"], 2, status=409)
    second_order = rig.repair_order("HALF", half_front["impression_id"], [[1, 1], [3, 1]])
    second_hit = rig.repair_execution(second_order["order_id"], 2)
    reclaim = rig.repair_execution(second_order["order_id"], 2, status=200)
    superseded = rig.repair_order_detail(first_order["order_id"])
    if not (late["error"] == "stale_order" and second_order["demand"] == [[3, 1]]
            and reclaim["repair_id"] == second_hit["repair_id"] != first_hit["repair_id"]
            and superseded["status"] == "superseded" and len(superseded["executions"]) == 1):
        raise AssertionError(("half", late, second_order["demand"], reclaim, superseded))
    summary["remeasure_and_replace"] = {
        "first_order_plan": [action["action_no"] for action in first_order["actions"]],
        "first_execution": first_hit,
        "late_command_after_remeasure": late["error"],
        "second_order_demand": second_order["demand"],
        "second_execution": second_hit,
        "reclaim_same_item": reclaim,
    }

    # 批次验收：已完成（含补印首执）、待补、无解各纸及缺墨出处。
    for action_no in greedy_plan:
        rig.repair_execution(greedy_order["order_id"], action_no)
    rig.repair_execution(left_order["order_id"], 1)
    batch = rig.inspect(["GREEDY", "HALF", "SPLIT", "SPLIT-R", "SPLIT-X"])
    observed = (
        [row["sheet_id"] for row in batch["completed"]],
        [(row["sheet_id"], row["reason"]) for row in batch["unfinished"]],
        [(row["sheet_id"], row["reason"]) for row in batch["unsolvable"]],
    )
    if observed != (["GREEDY", "HALF", "SPLIT"], [("SPLIT-R", "repair_pending")],
                    [("SPLIT-X", "repair_unsolvable")]):
        raise AssertionError(observed)
    # 重开后原验收与补印首执仍可复领。
    rig.stop_station()
    rig.start_station()
    retrieved = rig.receipt(batch["acceptance_id"])
    reclaimed_hit = rig.repair_execution(second_order["order_id"], 2, status=200)
    first_print = rig.repair_print(first_hit["repair_id"])
    if not (retrieved == batch and reclaimed_hit["repair_id"] == second_hit["repair_id"]
            and first_print == first_hit):
        raise AssertionError((retrieved == batch, reclaimed_hit, first_print))
    summary["acceptance_and_reclaim"] = {
        "completed": observed[0],
        "pending": observed[1],
        "unsolvable": observed[2],
        "repairs_cited": {row["sheet_id"]: [item["repair_id"] for item in row["repairs"]]
                          for row in batch["completed"]},
        "missing_ink_origin": batch["unsolvable"][0]["repair"],
        "retrieved_after_reopen_equals_original": retrieved == batch,
        "reclaimed_first_execution": reclaimed_hit,
    }
    return summary


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
        summary = {
            "nominal_commands": previews,
            "common_back": common,
            "first_east_request": pending,
            "invalid_east_command": rejected,
            "retrieved_first_acceptance": retrieved,
            "west_acceptance_after_printing": second,
        }
        summary["repair"] = repair_demo(rig)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the workshop sample over loopback HTTP")
    parser.add_argument("command", choices=("demo",))
    parser.parse_args()
    demo()
