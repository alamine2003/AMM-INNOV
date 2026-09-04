#!/usr/bin/env python3
"""Attend qu'une ou plusieurs dépendances TCP acceptent les connexions.

Usage :
    wait-for.py [--timeout 120] URL_OU_HOTE:PORT ...

Accepte des URL (postgres://user:pass@host:5432/db, redis://host:6379/0,
http://host:8000) ou des paires hote:port. Aucune dépendance hors bibliothèque
standard : le script est utilisable dans n'importe quelle image Python.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from urllib.parse import urlparse

DEFAULT_PORTS = {"postgres": 5432, "postgresql": 5432, "redis": 6379, "rediss": 6379,
                 "http": 80, "https": 443, "amqp": 5672, "smtp": 25}


def parse_target(target: str) -> tuple[str, int]:
    if "://" in target:
        parsed = urlparse(target)
        host = parsed.hostname or "localhost"
        port = parsed.port or DEFAULT_PORTS.get(parsed.scheme, 0)
    else:
        host, _, port_str = target.rpartition(":")
        host = host or target
        port = int(port_str) if port_str.isdigit() else 0
    if not port:
        raise ValueError(f"port introuvable dans la cible {target!r}")
    return host, port


def wait_for(host: str, port: int, timeout: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection((host, port), timeout=3):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", help="URL ou hote:port")
    parser.add_argument("--timeout", type=float, default=120.0, help="délai maximal en secondes")
    args = parser.parse_args(argv)

    for target in args.targets:
        host, port = parse_target(target)
        started = time.monotonic()
        print(f"[wait-for] {host}:{port} …", end=" ", flush=True)
        if not wait_for(host, port, args.timeout):
            print("indisponible")
            print(f"[wait-for] délai dépassé pour {host}:{port}", file=sys.stderr)
            return 1
        print(f"ok ({time.monotonic() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
