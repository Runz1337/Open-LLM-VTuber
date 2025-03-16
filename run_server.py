import os
import sys
import atexit
import argparse
from pathlib import Path
import tomli
import uvicorn
from loguru import logger
from upgrade import sync_user_config, select_language
from src.open_llm_vtuber.server import WebSocketServer
from src.open_llm_vtuber.config_manager import Config, read_yaml, validate_config
from pyngrok import ngrok  # Ngrok for exposing the server

# Set cache paths
os.environ["HF_HOME"] = str(Path(__file__).parent / "models")
os.environ["MODELSCOPE_CACHE"] = str(Path(__file__).parent / "models")

# Default values
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080  # Use a port that is more accessible in Colab


def get_version() -> str:
    with open("pyproject.toml", "rb") as f:
        pyproject = tomli.load(f)
    return pyproject["project"]["version"]


def init_logger(console_log_level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=console_log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | {message}",
        colorize=True,
    )
    logger.add(
        "logs/debug_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
        backtrace=True,
        diagnose=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Open-LLM-VTuber Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--hf_mirror", action="store_true", help="Use Hugging Face mirror")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Host to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
    return parser.parse_args()


@logger.catch
def run(console_log_level: str, host: str, port: int):
    init_logger(console_log_level)
    logger.info(f"Open-LLM-VTuber, version v{get_version()}")

    try:
        sync_user_config(logger=logger, lang=select_language())
    except Exception as e:
        logger.error(f"Error syncing user config: {e}")

    atexit.register(WebSocketServer.clean_cache)

    # Load configuration
    config: Config = validate_config(read_yaml("conf.yaml"))
    server_config = config.system_config

    # Use default or overridden values
    host = host or server_config.host or DEFAULT_HOST
    port = port or server_config.port or DEFAULT_PORT

    # Start ngrok tunnel
    ngrok.set_auth_token("2IwNxqGud7HOcTBJCALT9u05aRg_2g4D2jTgPi7RxridKLbBg")  # Your ngrok token
    public_url = ngrok.connect(port, "http")
    logger.info(f"ngrok tunnel '{public_url}' -> 'http://{host}:{port}'")

    # Ensure ngrok is disconnected on exit
    atexit.register(lambda: ngrok.disconnect(public_url))

    # Start the WebSocket server
    server = WebSocketServer(config=config)
    uvicorn.run(
        app=server.app,
        host=host,
        port=port,
        log_level=console_log_level.lower(),
    )


if __name__ == "__main__":
    args = parse_args()
    console_log_level = "DEBUG" if args.verbose else "INFO"
    
    if args.verbose:
        logger.info("Running in verbose mode")
    else:
        logger.info("Running in standard mode.")

    if args.hf_mirror:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    run(console_log_level=console_log_level, host=args.host, port=args.port)
    
