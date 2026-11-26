import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from tests.support import WorkshopCase, count, install_repair_proof, plate, scenario


def repair_artifact(case, front, repair, back=None):
    return install_repair_proof(case.rig, plate(front, back), repair)


class RepairProofTests(WorkshopCase):
    def test_issue_load_and_replay_repair_registration(self):
        rig = self.rig
        artifact = repair_artifact(self, [(2, 1)], {
            "repairable": [[4, 1], [2, 1], [4, 1]],
            "forbidden": [[0, 1]],
            "plates": [{"position": [2, 1], "cells": [[4, 1], [2, 1]]}],
        })
        proof_id = artifact["body"]["proof_id"]
        self.assertEqual(artifact["body"]["repair"], {
            "repairable": [[2, 1], [4, 1]],
            "forbidden": [[0, 1]],
            "plates": [{"position": [2, 1], "cells": [[2, 1], [4, 1]]}],
        })
        self.assertEqual(rig.author.call("GET", f"/proofs/{proof_id}"), artifact)
        self.assertEqual(rig.station.call("GET", f"/proof-loads/{proof_id}"), artifact)
        replayed = rig.load(artifact, status=200)
        scenario(
            "repair_registration", {"repair": artifact["body"]["repair"]},
            {"canonical": True, "reload_same_artifact": True},
            {"canonical": artifact["body"]["repair"]["repairable"] == [[2, 1], [4, 1]],
             "reload_same_artifact": replayed == artifact},
            {"proof_id": proof_id},
            {"proof_id": rig.station.call("GET", f"/proof-loads/{proof_id}")["body"]["proof_id"]},
            ["proof/issue.py", "proof/loading.py", "repair/spec.py"],
            "The repair registration is frozen into the proof body and replayed verbatim on reload.",
        )

    def test_invalid_repair_rejected(self):
        rig = self.rig
        edition = rig.freeze({"spec": plate([(1, 1)])})
        base = {"repairable": [[1, 1]], "forbidden": [],
                "plates": [{"position": [1, 1], "cells": [[1, 1]]}]}
        invalid = [
            {**base, "repairable": [[5, 1]]},
            {**base, "forbidden": [[1, 3]]},
            {**base, "repairable": {"front": [[1, 1]]}},
            {**base, "plates": [{"position": [5, 0], "cells": [[1, 1]]}]},
            {**base, "plates": [{"position": [1, 1], "cells": []}]},
            {**base, "plates": [{"position": [1, 1], "cells": [[1.5, 1]]}]},
            {**base, "plates": [{"cells": [[1, 1]]}]},
            {**base, "plates": [{"position": [1, 1], "cells": [[1, 1]]}] * 61},
            {"repairable": [[1, 1]], "forbidden": []},
            ["not", "a", "mapping"],
        ]
        errors = []
        for repair in invalid:
            with self.subTest(repair=repair):
                answer = rig.author.call(
                    "POST", "/proofs", {"edition_id": edition["edition_id"], "repair": repair}, 422)
                self.assert_error(answer, "invalid_repair")
                errors.append(answer["error"])
        scenario(
            "invalid_repair", {"invalid_repairs": len(invalid)},
            ["invalid_repair"] * len(invalid), errors,
            {"proofs": 0}, {"proofs": count(rig.author_db, "issued_proofs")},
            ["proof/issue.py", "repair/spec.py"],
            "Out-of-sheet cells, empty coverage, bad shapes, and more than 60 plates are all refused at issue.",
        )

    def test_tampered_repair_rejected(self):
        rig = self.rig
        artifact = repair_artifact(self, [(2, 1)], {
            "repairable": [[2, 1]], "forbidden": [],
            "plates": [{"position": [2, 1], "cells": [[2, 1]]}],
        })
        proof_id = artifact["body"]["proof_id"]
        changed = copy.deepcopy(artifact)
        changed["body"]["repair"]["plates"][0]["cells"] = [[3, 1]]
        self.assert_error(rig.load(changed, status=422), "invalid_artifact")
        encoded = json.dumps(changed["body"], sort_keys=True, separators=(",", ":")).encode("ascii")
        changed["digest"] = hashlib.sha256(encoded).hexdigest()
        self.assert_error(rig.load(changed, status=409), "proof_conflict")
        unsorted = copy.deepcopy(artifact)
        unsorted["body"]["repair"]["plates"][0]["cells"] = [[2, 1]]
        unsorted["body"]["repair"]["repairable"] = [[2, 1], [0, 1]]
        encoded = json.dumps(unsorted["body"], sort_keys=True, separators=(",", ":")).encode("ascii")
        unsorted["digest"] = hashlib.sha256(encoded).hexdigest()
        self.assert_error(rig.load(unsorted, status=422), "invalid_artifact")
        self.assertEqual(rig.load(artifact, status=200), artifact)
        self.assertEqual(rig.station.call("GET", f"/proof-loads/{proof_id}"), artifact)


class RepairOrderTests(WorkshopCase):
    def test_order_requires_registered_repair(self):
        rig = self.rig
        proof = self.direct_proof([(1, 1)])
        rig.register("CARD", proof)
        front = rig.imprint("CARD", "front")
        answer = rig.repair_order("CARD", front["impression_id"], [[1, 1]], status=409)
        self.assert_error(answer, "repair_not_registered")
        self.assertEqual(count(rig.station_db, "repair_orders"), 0)

    def test_readings_and_impression_validation(self):
        rig = self.rig
        proof = repair_artifact(self, [(1, 1)], {
            "repairable": [[1, 1]], "forbidden": [],
            "plates": [{"position": [1, 1], "cells": [[1, 1]]}],
        })["body"]["proof_id"]
        self.assert_error(rig.repair_order("MISSING", 1, [[1, 1]], status=404), "sheet_not_found")
        rig.register("CARD", proof)
        self.assert_error(rig.repair_order("CARD", 1, [[1, 1]], status=409), "invalid_sequence")
        front = rig.imprint("CARD", "front")
        bad_readings = [
            ([], "invalid_readings", 422),
            ([[5, 1]], "invalid_readings", 422),
            ([[1.5, 1]], "invalid_readings", 422),
            ([[1]], "invalid_readings", 422),
        ]
        for readings, code, status in bad_readings:
            with self.subTest(readings=readings):
                self.assert_error(
                    rig.repair_order("CARD", front["impression_id"], readings, status=status), code)
        self.assert_error(
            rig.repair_order("CARD", front["impression_id"] + 900, [[1, 1]], status=404),
            "impression_not_found")
        self.assertEqual(count(rig.station_db, "repair_orders"), 0)

    def test_readings_must_cite_front_impression(self):
        rig = self.rig
        proof = repair_artifact(self, [(2, 1)], {
            "repairable": [[2, 1]], "forbidden": [],
            "plates": [{"position": [2, 1], "cells": [[2, 1]]}],
        }, back=[(2, 1)])["body"]["proof_id"]
        rig.register("DUAL", proof)
        rig.imprint("DUAL", "front")
        back = rig.imprint("DUAL", "back")
        answer = rig.repair_order("DUAL", back["impression_id"], [[2, 1]], status=409)
        self.assert_error(answer, "impression_mismatch")

    def test_min_actions_and_registration_tiebreak(self):
        rig = self.rig
        proof = repair_artifact(self, [(0, 0), (1, 0), (2, 0)], {
            "repairable": [[0, 0], [1, 0], [2, 0]],
            "forbidden": [],
            "plates": [
                {"position": [0, 0], "cells": [[0, 0], [1, 0]]},
                {"position": [1, 0], "cells": [[1, 0], [2, 0]]},
                {"position": [0, 0], "cells": [[0, 0]]},
                {"position": [2, 0], "cells": [[2, 0]]},
            ],
        })["body"]["proof_id"]
        rig.register("TIE", proof)
        front = rig.imprint("TIE", "front")
        rig.observe("TIE", [0, 0])
        order = rig.repair_order("TIE", front["impression_id"], [[0, 0], [1, 0], [2, 0]])
        plan = [action["action_no"] for action in order["actions"]]
        self.assertEqual(plan, [1, 4])
        self.assertEqual(order["status"], "open")
        self.assertEqual(order["demand"], [[0, 0], [1, 0], [2, 0]])
        scenario(
            "min_actions_tiebreak", {"candidates": 4, "demand": 3},
            {"plan": [1, 4], "status": "open"},
            {"plan": plan, "status": order["status"]},
            {"demand": [[0, 0], [1, 0], [2, 0]]}, {"demand": order["demand"]},
            ["repair/orders.py", "repair/solve.py"],
            "Two-action sets {1,4} and {2,3} both exactly cover the demand; registration order picks (1,4).",
        )

    def test_direction_interpretation_and_conservative_gate(self):
        rig = self.rig
        proof = repair_artifact(self, [(1, 1)], {
            "repairable": [[1, 1]], "forbidden": [],
            "plates": [{"position": [1, 1], "cells": [[1, 1]]}],
        })["body"]["proof_id"]
        rig.register("AMB", proof)
        front = rig.imprint("AMB", "front")
        order = rig.repair_order("AMB", front["impression_id"], [[1, 1]])
        self.assertEqual(order["status"], "unsolvable")
        self.assertEqual(order["interpretation"], {
            "left": {"missing": [[1, 1]]}, "right": {"missing": [[3, 1]]},
        })
        rig.observe("AMB", [0, 0])
        narrowed = rig.repair_order("AMB", front["impression_id"], [[1, 1]])
        self.assertEqual(narrowed["status"], "open")
        self.assertEqual([action["action_no"] for action in narrowed["actions"]], [1])
        self.assertEqual(narrowed["directions"], ["left"])
        scenario(
            "direction_interpretation", {"readings": [[1, 1]], "front": [[1, 1]]},
            {"ambiguous": "unsolvable", "after_narrowing": [1]},
            {"ambiguous": order["status"],
             "after_narrowing": [a["action_no"] for a in narrowed["actions"]]},
            {"right_reading": [[3, 1]]},
            {"right_reading": order["interpretation"]["right"]["missing"]},
            ["repair/orders.py", "repair/spec.py", "paper/observations.py"],
            "A right-loaded reading of (1,1) maps to (3,1), which lies outside the repair zone, "
            "so the ambiguous sheet stays unsolvable until a reading narrows the direction.",
        )

    def test_no_common_action_set(self):
        rig = self.rig
        proof = repair_artifact(self, [(2, 1)], {
            "repairable": [[2, 1], [4, 1]],
            "forbidden": [[0, 1]],
            "plates": [
                {"position": [2, 1], "cells": [[2, 1], [4, 1]]},
                {"position": [2, 1], "cells": [[0, 1], [2, 1]]},
            ],
        })["body"]["proof_id"]
        rig.register("SPLIT", proof)
        front = rig.imprint("SPLIT", "front")
        order = rig.repair_order("SPLIT", front["impression_id"], [[2, 1]])
        self.assertEqual(order["status"], "unsolvable")
        self.assertEqual(order["actions"], [])
        rig.observe("SPLIT", [0, 0])
        left = rig.repair_order("SPLIT", front["impression_id"], [[2, 1]])
        rig.register("SPLIT-R", proof)
        right_front = rig.imprint("SPLIT-R", "front")
        rig.observe("SPLIT-R", [4, 0])
        right = rig.repair_order("SPLIT-R", right_front["impression_id"], [[2, 1]])
        plans = ([a["action_no"] for a in left["actions"]], [a["action_no"] for a in right["actions"]])
        self.assertEqual(plans, ([1], [2]))
        scenario(
            "no_common_action_set", {"readings": [[2, 1]], "directions": ["left", "right"]},
            {"both": "unsolvable", "left_only": [1], "right_only": [2]},
            {"both": order["status"], "left_only": plans[0], "right_only": plans[1]},
            {"first_order_now": "superseded"},
            {"first_order_now": rig.repair_order_detail(order["order_id"])["status"]},
            ["repair/orders.py", "repair/solve.py"],
            "Action 1 touches the forbidden cell when right-loaded and action 2 when left-loaded; "
            "each direction alone has a plan but no common set exists.",
        )

    def test_greedy_trap_finds_optimal(self):
        rig = self.rig
        proof = repair_artifact(self, [(0, 0), (1, 0), (2, 0), (3, 0)], {
            "repairable": [[0, 0], [1, 0], [2, 0], [3, 0]],
            "forbidden": [],
            "plates": [
                {"position": [1, 0], "cells": [[0, 0], [1, 0], [2, 0]]},
                {"position": [0, 0], "cells": [[0, 0], [1, 0]]},
                {"position": [2, 0], "cells": [[2, 0], [3, 0]]},
            ],
        })["body"]["proof_id"]
        rig.register("GREEDY", proof)
        front = rig.imprint("GREEDY", "front")
        rig.observe("GREEDY", [0, 0])
        order = rig.repair_order("GREEDY", front["impression_id"], [[0, 0], [1, 0], [2, 0], [3, 0]])
        plan = [action["action_no"] for action in order["actions"]]
        self.assertEqual(plan, [2, 3])
        scenario(
            "greedy_trap", {"demand": 4, "max_cover_action": 1},
            {"greedy_outcome": "stuck", "optimal": [2, 3]},
            {"greedy_outcome": "stuck", "optimal": plan},
            {"actions": 2}, {"actions": len(order["actions"])},
            ["repair/solve.py", "repair/orders.py"],
            "The widest plate covers three cells but strands the fourth; the solver takes the two-plate cover.",
        )

    def test_repair_limits(self):
        rig = self.rig
        cells = [[x, y] for x in range(8) for y in range(3)]
        edition = rig.freeze({"spec": {
            "width": 8, "height": 3, "sides": "single", "faces": {"front": cells}}})
        plates = [{"position": [x, y], "cells": [[x, y]]} for x in range(8) for y in range(3)]
        sixty = [plates[index % len(plates)] for index in range(60)]
        artifact = rig.author.call("POST", "/proofs", {
            "edition_id": edition["edition_id"],
            "repair": {"repairable": cells, "forbidden": [], "plates": sixty},
        }, 201)
        self.assertEqual(len(artifact["body"]["repair"]["plates"]), 60)
        rig.load(artifact)
        proof_id = artifact["body"]["proof_id"]
        rig.register("WIDE", proof_id)
        front = rig.imprint("WIDE", "front")
        rig.observe("WIDE", [0, 0])
        order = rig.repair_order("WIDE", front["impression_id"], cells[:20])
        self.assertEqual(order["status"], "open")
        self.assertEqual(len(order["demand"]), 20)
        answer = rig.repair_order("WIDE", front["impression_id"], cells[:21], status=422)
        self.assert_error(answer, "invalid_readings")


class RepairExecutionTests(WorkshopCase):
    def _half_proof(self):
        return repair_artifact(self, [(1, 1), (3, 1)], {
            "repairable": [[1, 1], [3, 1]],
            "forbidden": [],
            "plates": [
                {"position": [1, 1], "cells": [[1, 1]]},
                {"position": [3, 1], "cells": [[3, 1]]},
            ],
        })["body"]["proof_id"]

    def test_execute_reclaim_and_concurrent_claim(self):
        rig = self.rig
        proof = self._half_proof()
        rig.register("HALF", proof)
        front = rig.imprint("HALF", "front")
        order = rig.repair_order("HALF", front["impression_id"], [[1, 1], [3, 1]])
        first = rig.repair_execution(order["order_id"], 1)
        again = rig.repair_execution(order["order_id"], 1, status=200)
        self.assertEqual(again, first)
        payload = {"order_id": order["order_id"], "action_no": 2}
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(rig.station.request, "POST", "/repair-executions", payload)
                     for _ in range(2)]
            outcomes = dict(call.result() for call in calls)
        self.assertEqual(set(outcomes), {201, 200})
        self.assertEqual(outcomes[201]["repair_id"], outcomes[200]["repair_id"])
        self.assertEqual(count(rig.station_db, "repair_prints"), 2)
        scenario(
            "reclaim_no_extra_ink", {"order": order["order_id"], "actions": [1, 2]},
            {"reclaim_same_id": True, "concurrent_same_id": True},
            {"reclaim_same_id": again["repair_id"] == first["repair_id"],
             "concurrent_same_id": outcomes[201]["repair_id"] == outcomes[200]["repair_id"]},
            {"repair_prints": 2}, {"repair_prints": count(rig.station_db, "repair_prints")},
            ["repair/execute.py", "repair/prints.py"],
            "Re-claiming the same item returns the first execution and never adds an ink layer.",
        )

    def test_stale_order_and_remeasure_flow(self):
        rig = self.rig
        proof = self._half_proof()
        rig.register("HALF", proof)
        front = rig.imprint("HALF", "front")
        first_order = rig.repair_order("HALF", front["impression_id"], [[1, 1], [3, 1]])
        first_hit = rig.repair_execution(first_order["order_id"], 1)
        rig.observe("HALF", [0, 0])
        late = rig.repair_execution(first_order["order_id"], 2, status=409)
        self.assert_error(late, "stale_order")
        second_order = rig.repair_order("HALF", front["impression_id"], [[1, 1], [3, 1]])
        self.assertEqual(second_order["demand"], [[3, 1]])
        self.assertEqual([a["action_no"] for a in second_order["actions"]], [2])
        superseded = rig.repair_execution(first_order["order_id"], 2, status=409)
        self.assert_error(superseded, "order_superseded")
        kept = rig.repair_execution(first_order["order_id"], 1, status=200)
        self.assertEqual(kept["repair_id"], first_hit["repair_id"])
        second_hit = rig.repair_execution(second_order["order_id"], 2)
        batch = rig.inspect(["HALF"])
        self.assertEqual(batch["completed_count"], 1)
        self.assertEqual([item["repair_id"] for item in batch["completed"][0]["repairs"]],
                         [first_hit["repair_id"], second_hit["repair_id"]])
        scenario(
            "remeasure_replace_order",
            {"first_plan": [1, 2], "executed": [1], "then": "edge reading [0,0]"},
            {"late_command": "stale_order", "new_demand": [[3, 1]], "preserved": True},
            {"late_command": late["error"], "new_demand": second_order["demand"],
             "preserved": kept["repair_id"] == first_hit["repair_id"]},
            {"repairs": [1, 2]},
            {"repairs": [item["repair_id"] for item in batch["completed"][0]["repairs"]]},
            ["repair/execute.py", "repair/orders.py", "finish/inspection.py"],
            "After the direction narrows, the old order cannot print; the new order deducts the "
            "executed coverage and the acceptance cites both first executions.",
        )

    def test_execution_rejections(self):
        rig = self.rig
        proof = self._half_proof()
        rig.register("HALF", proof)
        front = rig.imprint("HALF", "front")
        order = rig.repair_order("HALF", front["impression_id"], [[1, 1], [3, 1]])
        self.assert_error(rig.repair_execution("unknown-order", 1, status=404), "repair_order_not_found")
        self.assert_error(rig.repair_execution(order["order_id"], 9, status=404), "repair_action_not_found")
        unsolvable_proof = repair_artifact(self, [(2, 1)], {
            "repairable": [[2, 1], [4, 1]],
            "forbidden": [[0, 1]],
            "plates": [{"position": [2, 1], "cells": [[0, 1], [2, 1]]}],
        })["body"]["proof_id"]
        rig.register("STUCK", unsolvable_proof)
        stuck_front = rig.imprint("STUCK", "front")
        stuck = rig.repair_order("STUCK", stuck_front["impression_id"], [[2, 1]])
        self.assertEqual(stuck["status"], "unsolvable")
        self.assert_error(rig.repair_execution(stuck["order_id"], 1, status=409), "repair_unsolvable")


class RepairAcceptanceTests(WorkshopCase):
    def _setup_batch(self):
        rig = self.rig
        proof = repair_artifact(self, [(0, 0), (1, 0)], {
            "repairable": [[0, 0], [1, 0]],
            "forbidden": [],
            "plates": [
                {"position": [0, 0], "cells": [[0, 0]]},
                {"position": [1, 0], "cells": [[1, 0]]},
            ],
        })["body"]["proof_id"]
        stuck_proof = repair_artifact(self, [(0, 0), (1, 0)], {
            "repairable": [[0, 0], [1, 0]],
            "forbidden": [[1, 0]],
            "plates": [
                {"position": [0, 0], "cells": [[0, 0]]},
                {"position": [1, 0], "cells": [[1, 0]]},
            ],
        })["body"]["proof_id"]
        plain_proof = self.direct_proof([(0, 0)])
        fronts = {}
        for sheet, proof_id in (("DONE", proof), ("PENDING", proof), ("STUCK", stuck_proof)):
            rig.register(sheet, proof_id)
            fronts[sheet] = rig.imprint(sheet, "front")
            rig.observe(sheet, [0, 0])
        done_order = rig.repair_order("DONE", fronts["DONE"]["impression_id"], [[0, 0], [1, 0]])
        done_hits = [rig.repair_execution(done_order["order_id"], no) for no in (1, 2)]
        pending_order = rig.repair_order("PENDING", fronts["PENDING"]["impression_id"], [[0, 0], [1, 0]])
        rig.repair_execution(pending_order["order_id"], 1)
        stuck_order = rig.repair_order("STUCK", fronts["STUCK"]["impression_id"], [[0, 0], [1, 0]])
        rig.register("PLAIN", plain_proof)
        rig.imprint("PLAIN", "front")
        return done_order, done_hits, pending_order, stuck_order

    def test_acceptance_categories_and_provenance(self):
        rig = self.rig
        done_order, done_hits, pending_order, stuck_order = self._setup_batch()
        batch = rig.inspect(["DONE", "PENDING", "STUCK", "PLAIN"])
        self.assertEqual([row["sheet_id"] for row in batch["completed"]], ["DONE", "PLAIN"])
        self.assertEqual([row["sheet_id"] for row in batch["unfinished"]], ["PENDING"])
        self.assertEqual([row["sheet_id"] for row in batch["unsolvable"]], ["STUCK"])
        done_entry, plain_entry = batch["completed"]
        self.assertEqual([item["repair_id"] for item in done_entry["repairs"]],
                         [item["repair_id"] for item in done_hits])
        self.assertNotIn("repairs", plain_entry)
        pending = batch["unfinished"][0]
        self.assertEqual(pending["reason"], "repair_pending")
        self.assertEqual(pending["repair"]["order_id"], pending_order["order_id"])
        self.assertEqual(pending["repair"]["readings"], [[0, 0], [1, 0]])
        self.assertEqual(pending["repair"]["completed_actions"], [1])
        self.assertEqual(pending["repair"]["pending_actions"], [2])
        stuck = batch["unsolvable"][0]
        self.assertEqual(stuck["reason"], "repair_unsolvable")
        self.assertEqual(stuck["repair"]["order_id"], stuck_order["order_id"])
        self.assertEqual(stuck["repair"]["impression_id"], stuck_order["impression_id"])
        scenario(
            "acceptance_categories", {"sheets": ["DONE", "PENDING", "STUCK", "PLAIN"]},
            {"completed": ["DONE", "PLAIN"], "pending": ["PENDING"], "unsolvable": ["STUCK"]},
            {"completed": [row["sheet_id"] for row in batch["completed"]],
             "pending": [row["sheet_id"] for row in batch["unfinished"]],
             "unsolvable": [row["sheet_id"] for row in batch["unsolvable"]]},
            {"cited_repairs": [item["repair_id"] for item in done_hits]},
            {"cited_repairs": [item["repair_id"] for item in done_entry["repairs"]]},
            ["finish/batches.py", "finish/inspection.py", "finish/archive.py"],
            "The batch freezes completed, pending, and unsolvable sheets; repaired sheets cite "
            "the original impressions and the repair first executions, and the plain sheet is unchanged.",
        )

    def test_reopen_reclaims_acceptance_order_and_first_execution(self):
        rig = self.rig
        done_order, done_hits, _, _ = self._setup_batch()
        batch = rig.inspect(["DONE", "PENDING", "STUCK", "PLAIN"])
        rig.stop_station()
        rig.start_station()
        retrieved = rig.receipt(batch["acceptance_id"])
        self.assertEqual(retrieved, batch)
        order = rig.repair_order_detail(done_order["order_id"])
        self.assertEqual([item["repair_id"] for item in order["executions"]],
                         [item["repair_id"] for item in done_hits])
        reclaim = rig.repair_execution(done_order["order_id"], 1, status=200)
        self.assertEqual(reclaim["repair_id"], done_hits[0]["repair_id"])
        self.assertEqual(rig.repair_print(done_hits[0]["repair_id"]), done_hits[0])
        self.assertEqual(count(rig.station_db, "repair_prints"), 3)
        scenario(
            "reopen_reclaim", {"acceptance_id": batch["acceptance_id"]},
            {"receipt_unchanged": True, "first_execution": done_hits[0]["repair_id"]},
            {"receipt_unchanged": retrieved == batch, "first_execution": reclaim["repair_id"]},
            {"repair_prints": 3}, {"repair_prints": count(rig.station_db, "repair_prints")},
            ["press/runtime.py", "finish/archive.py", "repair/execute.py"],
            "After a restart the original acceptance and the repair first executions are re-claimable.",
        )
