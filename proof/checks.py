from dataclasses import dataclass

from plate.geometry import FaceMap
from proof.layout import BACK_OFFSETS, LoadingDirection, ProofLayout, project_back, project_front


@dataclass(frozen=True)
class ProofCheckResult:
    nominal_front: FaceMap
    allowed: dict[LoadingDirection, tuple[str, ...]]
    eligible: bool

    def to_data(self):
        return {
            "nominal_front": [list(point) for point in self.nominal_front],
            "by_direction": {direction.value: list(commands) for direction, commands in self.allowed.items()},
            "eligible": self.eligible,
        }


def check_initial_alignment(layout: ProofLayout) -> ProofCheckResult:
    front = project_front(layout, "P")
    if front is None:
        return ProofCheckResult((), {}, False)
    if layout.sides == "single":
        return ProofCheckResult(front, {}, True)
    allowed = {
        direction: tuple(
            command for command in sorted(BACK_OFFSETS)
            if project_back(layout, direction, command) == front
        )
        for direction in LoadingDirection
    }
    return ProofCheckResult(front, allowed, any(allowed.values()))
