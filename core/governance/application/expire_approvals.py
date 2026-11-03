"""ExpireApprovals use-case: sweep pending/approved approvals past their expiry."""

from datetime import datetime, timezone

from core.governance.application.ports import ApprovalStorePort


class ExpireApprovals:
    def __init__(self, store: ApprovalStorePort) -> None:
        self._store = store

    def execute(self) -> int:
        """Expire all pending/approved approvals whose expiry has passed.
        Returns the number of approvals expired."""
        return self._store.expire_before(datetime.now(timezone.utc))
