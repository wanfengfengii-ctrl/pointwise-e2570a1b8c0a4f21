from concurrent.futures import ThreadPoolExecutor

from tests.support import WorkshopCase, scenario


def faces(rows):
    return [row["face"] for row in rows]


class PressTests(WorkshopCase):
    def test_single_sheet_and_sequence(self):
        rig = self.rig
        proof = self.direct_proof([(0, 0), (3, 1)])
        other = self.direct_proof([(1, 1)])
        self.assert_error(rig.register("CARD", "missing", status=404), "proof_not_loaded")
        rig.register("CARD", proof)
        self.assert_error(rig.register("CARD", other, status=409), "sheet_exists")
        self.assertEqual(rig.paper("CARD")["proof_id"], proof)
        self.assert_error(rig.imprint("CARD", "back", status=409), "invalid_sequence")
        self.assert_error(rig.imprint("CARD", "front", "Q", status=409), "incompatible")
        self.assertEqual(rig.impressions("CARD"), [])
        front = rig.imprint("CARD", "front", "S")
        self.assert_error(rig.imprint("CARD", "front", status=409), "already_printed")
        self.assert_error(rig.imprint("CARD", "back", status=409), "invalid_sequence")
        rows = rig.impressions("CARD")
        batch = rig.inspect(["CARD"])
        self.assertEqual(rows, [{key: value for key, value in front.items() if key != "status"}])
        scenario(
            "single", {"front": [[0, 0], [3, 1]], "command": "S"},
            {"position": [[1, 0], [4, 1]], "faces": ["front"]},
            {"position": front["position"], "faces": faces(rows)},
            [{"sheet_id": "CARD", "impression_ids": [front["impression_id"]]}],
            [{"sheet_id": item["sheet_id"], "impression_ids": [row["impression_id"] for row in item["impressions"]]}
             for item in batch["completed"]],
            ["press/positions.py", "press/imprint.py", "press/history.py", "finish/inspection.py"],
            "S adds one to each x coordinate, and a single-sided paper is complete after its one front impression.",
        )

    def test_double_offline_left_rejects_right(self):
        rig = self.rig
        proof = self.direct_proof([(1, 1)], [(1, 1)])
        rig.stop_author()
        rig.register("LEFT", proof)
        self.assert_error(rig.imprint("LEFT", "back", status=409), "invalid_sequence")
        self.assertEqual(rig.impressions("LEFT"), [])
        front = rig.imprint("LEFT", "front")
        observation = rig.observe("LEFT", [0, 0])
        self.assertEqual(observation["directions"], ["left"])
        refused = rig.imprint("LEFT", "back", "Q", status=409)
        self.assert_error(refused, "incompatible")
        self.assertEqual(faces(rig.impressions("LEFT")), ["front"])
        back = rig.imprint("LEFT", "back", "P")
        self.assertEqual(back["front_impression_id"], front["impression_id"])
        self.assert_error(rig.imprint("LEFT", "back", status=409), "already_printed")
        receipt = rig.inspect(["LEFT"])
        scenario(
            "double", {"front": [[1, 1]], "back": [[1, 1]], "edge": [0, 0], "attempts": ["Q", "P"]},
            {"rejected": "incompatible", "positions": [[[1, 1]], [[1, 1]]]},
            {"rejected": refused["error"], "positions": [row["position"] for row in rig.impressions("LEFT")]},
            [front["impression_id"], back["impression_id"]],
            [row["impression_id"] for item in receipt["completed"] for row in item["impressions"]],
            ["proof/loading.py", "paper/observations.py", "press/candidates.py", "press/imprint.py", "finish/inspection.py"],
            "The paper is left-loaded. Q lands at x=3 and P at x=1. The acceptance must cite the two issued impression IDs.",
        )

    def test_ambiguous_two_sheets_conflicting_reading_and_resume(self):
        rig = self.rig
        proof = self.direct_proof([(1, 1)], [(1, 1)])
        rig.stop_author()
        for sheet in ("A", "B"):
            rig.register(sheet, proof)
            rig.imprint(sheet, "front")
        self.assert_error(rig.observe("MISSING", [0, 0], status=404), "sheet_not_found")
        self.assert_error(rig.observe("A", [0, 3], status=422), "invalid_observation")
        self.assert_error(rig.observe("A", [3, 0], status=409), "conflicting_observation")
        self.assertEqual(rig.paper("A")["observations"], [])
        pending = rig.imprint("A", "back", status=409)
        self.assertEqual(faces(rig.impressions("A")), ["front"])
        neutral = rig.observe("B", [2, 0], probe="top")
        self.assertEqual(neutral["directions"], ["left", "right"])
        rig.observe("A", [0, 0])
        before = rig.paper("A")
        self.assert_error(rig.observe("A", [4, 0], status=409), "conflicting_observation")
        self.assertEqual(rig.paper("A"), before)
        self.assertEqual(rig.imprint("A", "back")["position"], [[1, 1]])
        other = rig.imprint("B", "back", status=409)
        first_batch = rig.inspect(["B", "A"])
        scenario(
            "ambiguous", {"proof_back": [[1, 1]], "first_command": "P", "only_A_edge": [0, 0]},
            {"before": "needs_orientation", "other": "needs_orientation", "B_directions": ["left", "right"]},
            {"before": pending["error"], "other": other["error"], "B_directions": rig.paper("B")["directions"]},
            {"completed": ["A"], "unfinished": ["B"], "B_faces": ["front"]},
            {"completed": [row["sheet_id"] for row in first_batch["completed"]],
             "unfinished": [row["sheet_id"] for row in first_batch["unfinished"]],
             "B_faces": faces(rig.impressions("B"))},
            ["paper/orientation.py", "paper/observations.py", "press/candidates.py", "press/imprint.py", "finish/batches.py"],
            "On the five-column sheet the left set is {P} and the right set is {Q}. Only A gets a directional reading before the first acceptance.",
        )
        rig.observe("B", [4, 0])
        self.assertEqual(rig.imprint("B", "back", "Q")["position"], [[1, 1]])
        self.assertEqual(faces(rig.impressions("B")), ["front", "back"])

    def test_common_command_and_shifted_actual_front(self):
        rig = self.rig
        common = self.direct_proof([(2, 1)], [(2, 1)])
        differing_back = self.direct_proof([(2, 1)], [(1, 1)])
        first_proof = rig.station.call("GET", f"/proof-loads/{common}")["body"]
        second_proof = rig.station.call("GET", f"/proof-loads/{differing_back}")["body"]
        self.assertEqual(first_proof["nominal_summary"], {"left": True, "right": True})
        self.assertEqual(first_proof["nominal_summary"], second_proof["nominal_summary"])
        rig.stop_author()
        rig.register("NOMINAL", common)
        rig.imprint("NOMINAL", "front")
        self.assertEqual(rig.imprint("NOMINAL", "back")["position"], [[2, 1]])
        rig.register("OTHER", differing_back)
        rig.imprint("OTHER", "front")
        self.assert_error(rig.imprint("OTHER", "back", status=409), "incompatible")
        self.assertEqual(rig.imprint("OTHER", "back", "S")["position"], [[2, 1]])
        rig.register("MOVED", common)
        front = rig.imprint("MOVED", "front", "S")
        self.assertEqual(front["position"], [[3, 1]])
        self.assert_error(rig.imprint("MOVED", "back", status=409), "needs_orientation")
        rig.observe("MOVED", [0, 0])
        self.assert_error(rig.imprint("MOVED", "back", status=409), "incompatible")
        self.assertEqual(faces(rig.impressions("MOVED")), ["front"])
        back = rig.imprint("MOVED", "back", "S")
        self.assertEqual(back["position"], [[3, 1]])
        self.assertEqual(back["front_impression_id"], front["impression_id"])
        self.assertEqual(rig.inspect(["MOVED", "NOMINAL", "OTHER"])["completed_count"], 3)

    def test_remaining_direction_without_a_legal_command(self):
        rig = self.rig
        proof = self.direct_proof([(3, 1)], [(1, 1)])
        rig.register("EDGE", proof)
        self.assertEqual(rig.imprint("EDGE", "front", "S")["position"], [[4, 1]])
        self.assert_error(rig.imprint("EDGE", "back", "R", status=409), "needs_orientation")
        rig.observe("EDGE", [0, 0])
        for command in ("P", "Q", "R", "S"):
            self.assert_error(rig.imprint("EDGE", "back", command, status=409), "incompatible")
        self.assertEqual(faces(rig.impressions("EDGE")), ["front"])
        self.assertEqual(rig.inspect(["EDGE"])["unfinished_count"], 1)

    def test_multi_point_mirror_and_duplicate_submission(self):
        rig = self.rig
        proof = self.direct_proof([(2, 1), (0, 0), (2, 1)], [(2, 1), (4, 0)])
        rig.register("TWICE", proof)
        front = rig.imprint("TWICE", "front")
        self.assertEqual(front["position"], [[0, 0], [2, 1]])
        rig.observe("TWICE", [4, 0])
        payload = {"sheet_id": "TWICE", "face": "back", "command": "P"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(rig.station.request, "POST", "/impressions", payload) for _ in range(2)]
            outcomes = dict(call.result() for call in calls)
        self.assertEqual(set(outcomes), {201, 409})
        self.assert_error(outcomes[409], "already_printed")
        self.assertEqual(outcomes[201]["position"], [[0, 0], [2, 1]])
        self.assertEqual(faces(rig.impressions("TWICE")), ["front", "back"])
