def solve_exact_cover(demand, candidates):
    """Choose one common action set that repairs every missing cell exactly once.

    candidates: iterable of (action_no, cells) in proof registration order.
    Coverage outside the demand does not take part in the cover. Among all
    feasible sets the smallest action count wins; ties are broken by comparing
    the sorted action numbers in registration order. Returns that sorted tuple
    of action numbers, or None when no common set exists.
    """
    demand = frozenset(demand)
    covers = []
    for action_no, cells in candidates:
        cover = frozenset(cells) & demand
        if cover:
            covers.append((action_no, cover))
    covers.sort(key=lambda item: item[0])
    memo = {frozenset(): ()}

    def solve(uncovered):
        if uncovered in memo:
            return memo[uncovered]
        compatible = [(action_no, cover) for action_no, cover in covers if cover <= uncovered]
        counts = {}
        for _, cover in compatible:
            for cell in cover:
                counts[cell] = counts.get(cell, 0) + 1
        best = None
        if all(cell in counts for cell in uncovered):
            target = min(uncovered, key=lambda cell: (counts[cell], cell))
            for action_no, cover in compatible:
                if target in cover:
                    rest = solve(uncovered - cover)
                    if rest is not None:
                        candidate = tuple(sorted((action_no, *rest)))
                        if best is None or (len(candidate), candidate) < (len(best), best):
                            best = candidate
        memo[uncovered] = best
        return best

    return solve(demand)
