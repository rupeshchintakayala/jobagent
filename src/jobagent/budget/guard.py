"""Per-user BYOK budget guard: estimate before call, refuse if cap would be exceeded."""
class BudgetExceeded(Exception): ...

class BudgetGuard:
    def __init__(self, cap_eur: float, spent_eur: float = 0.0):
        self.cap, self.spent = cap_eur, spent_eur
    def check(self, estimated_eur: float) -> None:
        if self.spent + estimated_eur > self.cap:
            raise BudgetExceeded(f"cap {self.cap} would be exceeded ({self.spent}+{estimated_eur})")
    def record(self, actual_eur: float) -> None:
        self.spent += actual_eur
