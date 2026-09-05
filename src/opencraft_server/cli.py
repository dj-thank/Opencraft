from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import secrets
import signal
import sys

from .auth import TokenAuthority
from .database import Database
from .http import OpenCraftHTTPServer, ServerContext
from .service import CanonicalWorldService


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="opencraft-server", description="OpenCraft local canonical-world reference server")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="run the loopback-first development server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--data-dir", type=Path, default=Path(".opencraft-data"))
    serve.add_argument("--prototype-dir", type=Path, default=Path("prototype"))
    serve.add_argument(
        "--unsafe-public-dev",
        action="store_true",
        help="allow a non-loopback bind; this does not make the reference server production-safe",
    )
    return parser


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


def serve(args) -> int:
    if not 1 <= args.port <= 65535:
        print("port must be between 1 and 65535", file=sys.stderr)
        return 2
    if not _is_loopback(args.host) and not args.unsafe_public_dev:
        print("refusing non-loopback bind without --unsafe-public-dev", file=sys.stderr)
        return 2
    if not _is_loopback(args.host):
        print("WARNING: the reference server is not production-safe and provides no TLS", file=sys.stderr)

    data_dir = args.data_dir.expanduser().resolve()
    database = Database(data_dir / "world.sqlite3")
    authority = TokenAuthority.from_data_directory(data_dir)
    service = CanonicalWorldService(database, authority)
    bootstrap_token = secrets.token_urlsafe(24)
    prototype = args.prototype_dir.expanduser().resolve()
    if not prototype.is_dir():
        prototype = None

    server = OpenCraftHTTPServer(
        (args.host, args.port),
        ServerContext(service=service, bootstrap_token=bootstrap_token, prototype_directory=prototype),
    )

    def stop(_signum, _frame):
        server.shutdown()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    print(f"OpenCraft local reference server: http://{args.host}:{server.server_address[1]}")
    print(f"Bootstrap token (local terminal only): {bootstrap_token}")
    print("This token creates the initial local world. It is never written to the database or logs.")
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        return serve(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
