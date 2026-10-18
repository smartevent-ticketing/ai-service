"""Composition root: the only place implementations are wired together."""

from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.infrastructure.settings import Settings
from smartevent_ai.infrastructure.knowledge_config import ReviewedRagConfig
from smartevent_ai.infrastructure.knowledge_runtime import RuntimePolicyReader


def build_chat(settings: Settings) -> tuple[ChatUseCase, ReadOnlyToolGateway]:
    transport = SafeBackendTransport(settings.backend_base_url)
    gateway = ReadOnlyToolGateway(settings.registry_path, settings.gates_path, transport)
    policies = RuntimePolicyReader(
        ReviewedRagConfig(settings.effective_config_dir),
        test_environment=settings.app_env == "test",
    )
    return ChatUseCase(RuleBasedVietnameseNLU(), gateway, policies=policies), gateway
