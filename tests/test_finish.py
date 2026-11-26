from tests.support import WorkshopCase, count, scenario


class FinishTests(WorkshopCase):
    def test_partial_batch_with_single_and_double(self):
        rig = self.rig
        double = self.direct_proof([(2, 1)], [(2, 1)])
        single = self.direct_proof([(0, 1)])
        impossible = self.direct_proof([(3, 1)], [(1, 1)])
        rig.register("DONE", double)
        rig.register("PART", double)
        rig.register("CARD", single)
        rig.register("BLANK", single)
        rig.register("UNFIT", impossible)
        front = rig.imprint("DONE", "front")
        back = rig.imprint("DONE", "back")
        rig.imprint("PART", "front")
        card = rig.imprint("CARD", "front")
        rig.imprint("UNFIT", "front", "S")
        rig.observe("UNFIT", [0, 0])
        self.assert_error(rig.imprint("UNFIT", "back", status=409), "incompatible")
        selected = ["PART", "DONE"]
        result = rig.inspect(selected)
        scenario(
            "partial", {"selected": selected, "DONE_faces": ["front", "back"], "PART_faces": ["front"]},
            {"complete": 1, "pending": 1, "complete_sheets": ["DONE"], "pending_sheets": ["PART"]},
            {"complete": result["completed_count"], "pending": result["unfinished_count"],
             "complete_sheets": [item["sheet_id"] for item in result["completed"]],
             "pending_sheets": [item["sheet_id"] for item in result["unfinished"]]},
            {"proof_id": double, "ids": [front["impression_id"], back["impression_id"]]},
            {"proof_id": result["completed"][0]["proof_id"],
             "ids": [item["impression_id"] for item in result["completed"][0]["impressions"]]},
            ["press/history.py", "finish/inspection.py", "finish/batches.py", "finish/archive.py"],
            "Only DONE has both actual sides, and the cited impressions are the original returned IDs.",
        )
        mixed = rig.inspect(["DONE", "UNFIT", "PART", "CARD", "BLANK"])
        self.assertEqual([item["sheet_id"] for item in mixed["completed"]], ["CARD", "DONE"])
        self.assertEqual([item["sheet_id"] for item in mixed["unfinished"]], ["BLANK", "PART", "UNFIT"])
        self.assertEqual([row["impression_id"] for row in mixed["completed"][0]["impressions"]], [card["impression_id"]])

    def test_invalid_batch_membership_and_empty_batch(self):
        rig = self.rig
        proof = self.direct_proof([(0, 1)])
        rig.register("CARD", proof)
        rig.imprint("CARD", "front")
        self.assert_error(rig.inspect(["CARD", "CARD"], status=409), "duplicate_sheet")
        self.assert_error(rig.inspect(["CARD", "UNKNOWN"], status=404), "sheet_not_found")
        self.assert_error(rig.inspect("CARD", status=400), "invalid_request")
        self.assertEqual(count(rig.station_db, "acceptances"), 0)
        empty = rig.inspect([])
        self.assertEqual(empty["completed"], [])
        self.assertEqual(empty["unfinished"], [])
        self.assertEqual((empty["completed_count"], empty["unfinished_count"]), (0, 0))
        self.assertEqual(rig.receipt(empty["acceptance_id"]), empty)

    def test_reopen_after_completion_and_unknown_receipt(self):
        rig = self.rig
        finished = self.direct_proof([(0, 0)])
        pending = self.direct_proof([(1, 1)], [(1, 1)])
        rig.stop_author()
        rig.register("CARD", finished)
        rig.register("LATER", pending)
        card = rig.imprint("CARD", "front")
        first_front = rig.imprint("LATER", "front")
        first = rig.inspect(["LATER", "CARD"])
        self.assertEqual([row["sheet_id"] for row in first["completed"]], ["CARD"])
        self.assertEqual([row["sheet_id"] for row in first["unfinished"]], ["LATER"])
        self.assertEqual(first["completed"][0]["impressions"][0]["impression_id"], card["impression_id"])
        rig.observe("LATER", [0, 0])
        back = rig.imprint("LATER", "back")
        rig.stop_station()
        rig.start_station()
        old = rig.receipt(first["acceptance_id"])
        self.assertEqual(rig.receipt(first["acceptance_id"]), old)
        new = rig.inspect(["LATER"])
        self.assertNotEqual(new["acceptance_id"], first["acceptance_id"])
        self.assert_error(rig.receipt("unknown", status=404), "acceptance_not_found")
        scenario(
            "reopen", {"old_acceptance_id": first["acceptance_id"], "later_back_id": back["impression_id"]},
            first, old,
            {"sheet_id": "LATER", "impression_ids": [first_front["impression_id"], back["impression_id"]]},
            {"sheet_id": new["completed"][0]["sheet_id"],
             "impression_ids": [item["impression_id"] for item in new["completed"][0]["impressions"]]},
            ["press/runtime.py", "finish/batches.py", "finish/archive.py"],
            "The original HTTP response is the snapshot oracle. The next inspection can show both actual impressions of LATER.",
        )
