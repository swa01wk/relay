import os

import uvicorn

from relay_gateway.app import create_app

app = create_app()


def run() -> None:
    host = os.environ.get("RELAY_GATEWAY_HOST", "0.0.0.0")
    port = int(os.environ.get("RELAY_GATEWAY_PORT", "8080"))
    uvicorn.run("relay_gateway.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
