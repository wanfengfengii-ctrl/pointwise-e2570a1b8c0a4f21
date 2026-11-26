from finish.archive import store_acceptance
from finish.inspection import check_sheet_completion
from press.history import read_print_facts
from workshop import BusinessError, identifier, transaction


def inspect_batch(db, sheet_ids):
    if not isinstance(sheet_ids, list):
        raise BusinessError("invalid_request", "sheet_ids must be an array.")
    ids = [identifier(sheet_id, "sheet_id") for sheet_id in sheet_ids]
    if len(ids) != len(set(ids)):
        raise BusinessError("duplicate_sheet", "List each paper at most once.", 409)
    completed = []
    unfinished = []
    with transaction(db, write=True):
        for sheet_id in sorted(ids):
            result = check_sheet_completion(read_print_facts(db, sheet_id))
            if result.complete:
                completed.append(result.entry)
            else:
                unfinished.append(result.entry)
        return store_acceptance(db, completed, unfinished)
