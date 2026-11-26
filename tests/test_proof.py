import copy
import hashlib
import json
import sqlite3
from contextlib import closing

from tests.support import WorkshopCase, count, plate, scenario


class ProofTests(WorkshopCase):
    def test_normal_proof_and_frozen_revision(self):
        rig = self.rig
        original = plate([(1, 1)], [(1, 1)])
        edited = plate([(2, 1)], [(2, 1)])
        rig.author.call("PUT", "/drafts/poster", {"spec": original})
        first = rig.freeze({"draft_id": "poster"})
        artifact = rig.issue(first["edition_id"])
        rig.load(artifact)
        rig.author.call("PUT", "/drafts/poster", {"spec": edited})
        second = rig.freeze({"draft_id": "poster"})
        self.assertNotEqual(first["edition_id"], second["edition_id"])
        self.assertEqual(second["spec"], edited)
        self.assertEqual(rig.author.call("GET", f"/editions/{first['edition_id']}"), first)
        reissued = rig.issue(first["edition_id"])
        self.assertNotEqual(artifact["body"]["proof_id"], reissued["body"]["proof_id"])
        proof_id = artifact["body"]["proof_id"]
        self.assertEqual(rig.author.call("GET", f"/proofs/{proof_id}"), artifact)
        loaded = rig.station.call("GET", f"/proof-loads/{proof_id}")
        self.assertEqual(loaded, artifact)
        nominal = rig.preview(first["edition_id"])["by_direction"]
        self.assertEqual(rig.preview(second["edition_id"])["by_direction"], {"left": ["P"], "right": ["P"]})
        scenario(
            "normal_proof", {"original": original, "edit": edited},
            {"layout": original, "commands": {"left": ["P"], "right": ["Q"]}},
            {"layout": reissued["body"]["layout"], "commands": nominal},
            {"edition_id": first["edition_id"], "layout": original},
            {key: loaded["body"][key] for key in ("edition_id", "layout")},
            ["plate/revisions.py", "proof/checks.py", "proof/issue.py", "proof/loading.py"],
            "At x=1 on a five-column sheet, left P and right Q both land at x=1. Editing a draft cannot alter a prior numbered edition.",
        )

    def test_bad_plate(self):
        rig = self.rig
        valid = plate([(0, 0)], [(4, 1)])
        rig.freeze({"spec": valid})
        invalid = [
            plate([(0, 0)], [(5, 1)]), plate([(0, 0)], []), plate([], [(4, 1)]),
            plate([(0, 0)], [(4, 3)]), plate([(0, 0)], [(-1, 1)]),
            plate([(True, 0)], [(4, 1)]), plate([(0.5, 0)], [(4, 1)]),
            {**valid, "faces": {"front": [[0, 0]]}}, {**valid, "height": 0},
        ]
        errors = []
        for spec in invalid:
            with self.subTest(spec=spec):
                rig.author.call("PUT", "/drafts/check", {"spec": spec})
                answer = rig.freeze({"draft_id": "check"}, status=422)
                self.assert_error(answer, "invalid_layout")
                errors.append(answer["error"])
        scenario(
            "bad_plate", {"valid_control": valid, "invalid_drafts": invalid},
            ["invalid_layout"] * len(invalid), errors,
            {"editions": 1, "proofs": 0},
            {"editions": count(rig.author_db, "editions"), "proofs": count(rig.author_db, "issued_proofs")},
            ["plate/geometry.py", "plate/revisions.py"],
            "Only the control has all required points in the integer rectangle 0≤x<5, 0≤y<3.",
        )

    def test_nominal_calculation_incompatible_and_one_direction(self):
        rig = self.rig
        unusable = rig.freeze({"spec": plate([(1, 1)], [(1, 0)])})
        result = rig.preview(unusable["edition_id"])
        self.assertEqual(result["nominal_front"], [[1, 1]])
        self.assertEqual(result["by_direction"], {"left": [], "right": []})
        self.assertFalse(result["eligible"])
        self.assert_error(rig.issue(unusable["edition_id"], status=409), "initial_incompatible")
        self.assert_error(rig.issue("unknown", status=404), "edition_not_found")
        self.assertEqual(count(rig.author_db, "issued_proofs"), 0)
        one_direction = rig.freeze({"spec": plate([(0, 1)], [(0, 1)])})
        preview = rig.preview(one_direction["edition_id"])
        self.assertEqual(preview["by_direction"], {"left": ["P"], "right": []})
        self.assertTrue(preview["eligible"])
        rig.load(rig.issue(one_direction["edition_id"]))

    def test_wrong_proof_cannot_replace_loaded_copy(self):
        rig = self.rig
        artifact = rig.install({"spec": plate([(1, 1)], [(1, 1)])})
        proof_id = artifact["body"]["proof_id"]
        rig.register("BEFORE", proof_id)
        other = rig.freeze({"spec": plate([(2, 1)], [(2, 1)])})
        mismatch = rig.load(artifact, status=409, edition_id=other["edition_id"])
        self.assert_error(mismatch, "proof_origin_mismatch")
        self.assert_error(rig.load(artifact, status=409, proof_id="different"), "proof_origin_mismatch")
        self.assert_error(rig.register("UNLOADED", "different", status=404), "proof_not_loaded")
        changed = copy.deepcopy(artifact)
        changed["body"]["layout"]["faces"]["back"] = [[2, 1]]
        self.assert_error(rig.load(changed, status=422), "invalid_artifact")
        encoded = json.dumps(changed["body"], sort_keys=True, separators=(",", ":")).encode("ascii")
        changed["digest"] = hashlib.sha256(encoded).hexdigest()
        self.assert_error(rig.load(changed, status=409), "proof_conflict")
        self.assertEqual(rig.load(artifact, status=200), artifact)
        after = rig.register("AFTER", proof_id)
        scenario(
            "wrong_proof", {"declared": other["edition_id"], "inside": artifact["body"]["edition_id"]},
            "proof_origin_mismatch", mismatch["error"],
            {"proof_id": proof_id, "stored": artifact},
            {"proof_id": after["proof_id"], "stored": rig.station.call("GET", f"/proof-loads/{proof_id}")},
            ["proof/loading.py", "proof/http.py", "paper/intake.py"],
            "Two independently allocated edition numbers differ, while the original artifact remains the one previously loaded.",
        )

    def test_seed_preserves_edits_and_backfills_missing(self):
        rig = self.rig
        changed = plate([(3, 1)], [(3, 1)])
        original_missing = rig.author.call("GET", "/drafts/community-split")
        rig.author.call("PUT", "/drafts/community-common", {"spec": changed})
        rig.stop_author()
        with closing(sqlite3.connect(rig.author_db)) as db, db:
            db.execute("DELETE FROM drafts WHERE draft_id = ?", ("community-split",))
        self.assertEqual(count(rig.author_db, "drafts"), 2)
        rig.start_author()
        self.assertEqual(rig.author.call("GET", "/drafts/community-common")["spec"], changed)
        self.assertEqual(rig.author.call("GET", "/drafts/community-split"), original_missing)
        self.assertEqual(count(rig.author_db, "drafts"), 3)
        rig.stop_author()
        rig.start_author()
        self.assertEqual(count(rig.author_db, "drafts"), 3)
        self.assertEqual(rig.freeze({"draft_id": "community-common"})["spec"], changed)
        repaired = rig.install({"draft_id": "community-split"})
        self.assertEqual(repaired["body"]["layout"], original_missing["spec"])
