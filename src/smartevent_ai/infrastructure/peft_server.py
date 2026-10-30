"""Local GPU entrypoint: load the configured checkpoint before accepting chat."""

import uvicorn

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.infrastructure.settings import Settings
from smartevent_ai.domain.dialogue import DialogueState


def main() -> None:
    app = create_app(Settings())
    nlu = app.state.chat._nlu
    if isinstance(nlu, PeftTransformerNLU):
        nlu._ensure_loaded()
        nlu.parse("Xin chào", DialogueState())
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
