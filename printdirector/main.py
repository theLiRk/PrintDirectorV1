import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import uvicorn

from .app import Runtime
from .config import ConfigurationError, load_config
from .overlay import create_app
from .utils.logging import setup_logging


async def serve(args):
    try:
        cfg = load_config(args.config)
    except ConfigurationError as exc:
        print(f"PrintDirector configuration error: {exc}", file=sys.stderr)
        return 2

    if (
        not cfg.overlay.allow_lan
        and cfg.overlay.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        print(
            "PrintDirector configuration error: overlay host must be "
            "localhost/127.0.0.1 unless allow_lan is enabled",
            file=sys.stderr,
        )
        return 2

    config_path = Path(args.config).resolve()
    log_path = setup_logging(cfg.logging, config_path.parent)
    if log_path:
        logging.info("Persistent log: %s", log_path)

    if not args.demo and not os.getenv(cfg.obs.password_env) and not cfg.obs.password:
        logging.warning(
            "OBS password is not configured; OBS authentication may reject connections"
        )

    logging.info("PrintDirector starting")
    runtime = Runtime(cfg, args.demo, config_path)
    app = create_app(runtime)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=cfg.overlay.host,
            port=cfg.overlay.port,
            log_level=cfg.logging.level.lower(),
            log_config=None,
        )
    )
    await runtime.start()
    try:
        await server.serve()
    except asyncio.CancelledError:
        pass
    finally:
        await runtime.stop()
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(serve(args)))


if __name__ == "__main__":
    main()
