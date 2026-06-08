from __future__ import annotations

import argparse

from src.web_app import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="股指期货升贴水监控 Web 服务")
    parser.add_argument("--port", type=int, default=5005, help="Web 服务端口")
    args = parser.parse_args()
    run_server(args.port)


if __name__ == "__main__":
    main()
