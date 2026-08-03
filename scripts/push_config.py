#!/usr/bin/env python3
"""
Push changed config files to homelab hosts via rsync.

Dependencies:
    pip install pyyaml
    rsync must be available on PATH (standard on Linux/macOS/WSL)
    SSH key access to each host (see push_hosts.yaml)

Config file:
    push_hosts.yaml must sit alongside this script.
    It defines two sections:
      - servers: named aliases for host IPs (used with --server)
      - services: named file-push targets, each with a list of local->remote mappings

Usage:
    # List all services and servers
    python push_config.py --help

    # Push a single service by name or numeric ID
    python push_config.py traefik-master
    python push_config.py 2

    # Push all services on a server (by name or IP)
    python push_config.py --server komodo-server
    python push_config.py --server 192.168.1.62

    # Preview without pushing (works for both modes)
    python push_config.py traefik-master --dry-run
    python push_config.py --server komodo-server --dry-run

Notes:
    - rsync uses --checksum so content changes are detected even when
      timestamps are unreliable (e.g. after a git checkout).
    - If both a positional target and --server are given, --server wins.
    - Files listed in push_hosts.yaml that don't exist locally are skipped
      with a warning rather than erroring out.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, TypedDict

import yaml


class FileMapping(TypedDict):
    local: str
    remote: str


class Service(TypedDict):
    id: int
    name: str
    host: str
    user: str
    key: str
    files: list[FileMapping]


class Server(TypedDict):
    name: str
    ip: str


# Bare IPs in these ranges are accepted directly by --server without needing a named alias
PRIVATE_IP_PREFIXES = ["192.168.", "10.", "172.16.", "172.17.", "172.18."]

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
HOSTS_FILE = SCRIPT_DIR / "push_hosts.yaml"


def load_config() -> tuple[list[Server], list[Service]]:
    with open(HOSTS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("servers", []), data.get("services", [])


def service_table(services: list[Service]) -> str:
    lines = [f"  {'ID':<4} {'Name':<22} {'Host'}"]
    lines.append("  " + "-" * 40)
    for svc in services:
        lines.append(f"  {svc['id']:<4} {svc['name']:<22} {svc['host']}")
    return "\n".join(lines)


def server_table(servers: list[Server]) -> str:
    lines = [f"  {'Name':<20} {'IP'}"]
    lines.append("  " + "-" * 36)
    for srv in servers:
        lines.append(f"  {srv['name']:<20} {srv['ip']}")
    return "\n".join(lines)


def resolve_service(target: str, services: list[Service]) -> Optional[Service]:
    for svc in services:
        if str(svc["id"]) == target or svc["name"] == target:
            return svc
    return None


def resolve_server_ip(target: str, servers: list[Server]) -> Optional[str]:
    for srv in servers:
        if srv["name"] == target or srv["ip"] == target:
            return srv["ip"]
    if any(target.startswith(p) for p in PRIVATE_IP_PREFIXES):
        return target
    return None


def push(svc: Service, dry_run: bool = False) -> tuple[int, int]:
    key = os.path.expanduser(svc["key"])
    ssh_opt = f"ssh -i {key} -o StrictHostKeyChecking=accept-new"
    files = svc["files"]

    if not files:
        print(f"  No files configured for '{svc['name']}' — skipping.")
        return 0, 0

    ok = failed = 0
    for entry in files:
        local = REPO_ROOT / entry["local"]
        remote = f"{svc['user']}@{svc['host']}:{entry['remote']}"

        if not local.exists():
            print(f"  SKIP  {entry['local']}  (file not found)")
            continue

        # --checksum catches content changes even when timestamps are unreliable (e.g. after git checkout)
        # --stats gives a parseable summary including "Number of regular files transferred"
        cmd = ["rsync", "-avz", "--checksum", "--stats", "-e", ssh_opt, str(local), remote]
        if dry_run:
            cmd.insert(1, "--dry-run")

        label = "DRY " if dry_run else ""
        print(f"  {label}-> {entry['local']}  =>  {remote}", end="", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            transferred = 0
            for line in result.stdout.splitlines():
                if line.startswith("Number of regular files transferred:"):
                    transferred = int(line.split(":")[1].strip().replace(",", ""))
            print(f"  [{'transferred' if transferred else 'no changes'}]")
            ok += 1
        else:
            print(f"  [ERROR]")
            print(f"     {result.stderr.strip()}")
            failed += 1

    return ok, failed


def main():
    try:
        servers, services = load_config()
    except Exception as e:
        print(f"ERROR: could not load {HOSTS_FILE}: {e}")
        sys.exit(1)

    epilog = (
        f"Services:\n{service_table(services)}\n\n"
        f"Servers:\n{server_table(servers)}\n\n"
        "Pass a service name/ID, or use --server with a server name/IP."
    )

    parser = argparse.ArgumentParser(
        description="Push config files to homelab hosts via rsync.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument("target", nargs="?", help="Service name or ID")
    parser.add_argument("--server", metavar="NAME_OR_IP", help="Push all services on this server")
    parser.add_argument("--dry-run", action="store_true", help="Preview without pushing")

    args = parser.parse_args()

    if not args.target and not args.server:
        parser.print_help()
        sys.exit(0)

    # --server takes precedence; target is ignored if both are supplied
    if args.server:
        ip = resolve_server_ip(args.server, servers)
        if not ip:
            print(f"Unknown server '{args.server}'. Run with --help to list servers.")
            sys.exit(1)

        matched = [svc for svc in services if svc["host"] == ip]
        if not matched:
            print(f"No services configured for server '{args.server}' ({ip}).")
            sys.exit(0)

        total_ok = total_failed = 0
        for svc in matched:
            print(f"\n--- {svc['name']} ({svc['host']}) ---")
            ok, failed = push(svc, dry_run=args.dry_run)
            total_ok += ok
            total_failed += failed

        print(f"\nTotal: {total_ok} pushed, {total_failed} failed")
        return

    svc = resolve_service(args.target, services)
    if not svc:
        print(f"Unknown service '{args.target}'. Run with --help to list services.")
        sys.exit(1)

    print(f"\n--- {svc['name']} ({svc['host']}) ---")
    ok, failed = push(svc, dry_run=args.dry_run)
    print(f"\n  {ok} pushed, {failed} failed")


if __name__ == "__main__":
    main()
