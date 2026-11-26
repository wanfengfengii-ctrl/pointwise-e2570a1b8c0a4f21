from finish.archive import store_acceptance
from finish.inspection import check_sheet_completion
from press.history import read_print_facts
from repair.orders import read_latest_order
from repair.prints import read_sheet_repair_prints
from workshop import BusinessError, identifier, transaction


def inspect_batch(db, sheet_ids):
    if not isinstance(sheet_ids, list):
        raise BusinessError("invalid_request", "sheet_ids must be an array.")
    ids = [identifier(sheet_id, "sheet_id") for sheet_id in sheet_ids]
    if len(ids) != len(set(ids)):
        raise BusinessError("duplicate_sheet", "List each paper at most once.", 409)
    completed = []
    unfinished = []
    unsolvable = []
    buckets = {"complete": completed, "unfinished": unfinished, "unsolvable": unsolvable}
    with transaction(db, write=True):
        for sheet_id in sorted(ids):
            facts = read_print_facts(db, sheet_id)
            front = next((item for item in facts.impressions if item.face == "front"), None)
            order = read_latest_order(db, sheet_id)
            prints = read_sheet_repair_prints(db, sheet_id, front.impression_id) if front else ()
            result = check_sheet_completion(facts, order, prints)
            buckets[result.category].append(result.entry)
        return store_acceptance(db, completed, unfinished, unsolvable)
