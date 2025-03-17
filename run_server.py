import os
import sys
import atexit
import argparse
import socket
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
DEFAULT_PORT = 8080  # Initial port to try

def find_free_port(start_port: int) -> int:
    """Return the first free port starting from start_port."""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((DEFAULT_HOST, port))
                # If bind succeeds, the port is free.
                return port
            except OSError:
                port += 1

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

    # Use provided or default host/port values
    host = host or server_config.host or DEFAULT_HOST
    desired_port = port or server_config.port or DEFAULT_PORT

    # Automatically find a free port starting at the desired_port
    free_port = find_free_port(desired_port)
    if free_port != desired_port:
        logger.info(f"Desired port {desired_port} is in use. Using available port {free_port} instead.")
    port = free_port

    # Start ngrok tunnel on the chosen port
    ngrok.set_auth_token("2IwNxqGud7HOcTBJCALT9u05aRg_2g4D2jTgPi7RxridKLbBg")  # Your ngrok token
    public_url = ngrok.connect(port, "http")
    logger.info(f"ngrok tunnel '{public_url}' -> 'http://{host}:{port}'")
    js_file_path = "frontend/assets/main-DsLaT6SU.js"  # Adjust path as needed
    ws_url=str(public_url).replace("https", "wss")
    os.environ["WS_NGROK_URL"] = ws_url
    os.environ["BASE_NGROK_URL"] = str(public_url)

    with open(js_file_path, "r", encoding="utf-8") as file:
       js_content = file.read()

# Replace old URLs with new Ngrok ones
    js_content = js_content.replace("ws://localhost:12393", ws_url)
    js_content = js_content.replace("http://localhost:12393", str(public_url))

# Save the updated JavaScript file
    with open(js_file_path, "w", encoding="utf-8") as file:
       file.write(js_content)
    # Ensure ngrok is disconnected on exit
    atexit.register(lambda: ngrok.disconnect(public_url))

    # Start the WebSocket server using uvicorn
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
