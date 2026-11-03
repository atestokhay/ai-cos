"""SelectModel use-case: resolve an explicit model_id or raise if not found / disabled."""

from core.model_router.application.ports import ModelRegistryPort
from core.model_router.domain.models import ModelSpec


class ModelNotFound(Exception):
    pass


class ModelDisabled(Exception):
    pass


class SelectModel:
    def __init__(self, registry: ModelRegistryPort) -> None:
        self._registry = registry

    def __call__(self, model_id: str) -> ModelSpec:
        spec = self._registry.get(model_id)
        if not spec.enabled:
            raise ModelDisabled(model_id)
        return spec
