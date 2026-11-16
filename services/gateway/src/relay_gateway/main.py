import os

import uvicorn

from relay_gateway.app import create_app
from relay_gateway.core.container import session_repository
from relay_gateway.core.logs import configure_logging

app = create_app()


def run() -> None:
    # One handler for Relay and uvicorn logs: redacts session tokens, JSON with RELAY_LOG_FORMAT=json.
    configure_logging(agent_for_session=session_repository.agent_label)
    host = os.environ.get("RELAY_GATEWAY_HOST", "0.0.0.0")
    port = int(os.environ.get("RELAY_GATEWAY_PORT", "8080"))
    uvicorn.run("relay_gateway.main:app", host=host, port=port, reload=False, log_config=None)


if __name__ == "__main__":
    run()
