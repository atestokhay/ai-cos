"""RouteRequest use-case: resolve an ordered fallback chain of ModelSpec candidates."""

from core.contracts.model_router import ModelCallRequest
from core.model_router.application.ports import ModelRegistryPort
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier


class RouteRequest:
    """Resolves explicit model_id or selects by tier + required capabilities.

    Returns an ordered list of enabled ModelSpec candidates for the execution
    pipeline to try in sequence. Returns [] when no candidates match; never raises.
    """

    def __init__(self, registry: ModelRegistryPort) -> None:
        self._registry = registry

    def __call__(
        self,
        request: ModelCallRequest,
        required_capabilities: frozenset[ModelCapability] | None = None,
        tier: ProviderTier | None = None,
    ) -> list[ModelSpec]:
        required = required_capabilities or frozenset()

        if request.model_id:
            try:
                spec = self._registry.get(request.model_id)
            except KeyError:
                return []
            if not spec.enabled:
                return []
            if required and not required.issubset(spec.capabilities):
                return []
            return [spec]

        if tier is None:
            return []

        candidates = [
            s
            for s in self._registry.list_by_tier(tier)
            if s.enabled and required.issubset(s.capabilities)
        ]
        return candidates
