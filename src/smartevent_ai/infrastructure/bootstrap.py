"""Composition root: the only place implementations are wired together."""

from smartevent_ai.adapters.outbound.ollama_nlu import OllamaNLU
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.ports import LanguageUnderstanding
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

    nlu: LanguageUnderstanding
    if settings.nlu_backend == "ollama":
        nlu = OllamaNLU(
            base_url=settings.ollama_base_url,
            model=settings.ollama_nlu_model,
            timeout=settings.ollama_timeout_seconds,
        )
    elif settings.nlu_backend == "peft":
        nlu = PeftTransformerNLU(
            adapter_path=settings.nlu_adapter_path,
            base_model_name=settings.nlu_base_model,
            load_4bit=settings.nlu_load_4bit,
        )
    else:
        nlu = RuleBasedVietnameseNLU()

    return ChatUseCase(nlu, gateway, policies=policies), gateway


