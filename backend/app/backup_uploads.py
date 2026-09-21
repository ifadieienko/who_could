"""Stream a companion archive for database backups. No secrets or DB data."""

import sys, tarfile, re
from pathlib import Path
from .repair_files import storage

PATTERN = re.compile(r"^[a-f0-9]{32}(\.thumb)?\.jpg$")


def main():
    root = storage()
    if sys.argv[1] == "export":
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
            for p in root.iterdir():
                if p.is_file() and not p.is_symlink() and PATTERN.fullmatch(p.name):
                    tar.add(p, arcname=p.name, recursive=False)
    elif sys.argv[1] == "restore":
        with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as tar:
            for m in tar:
                if (
                    not m.isfile()
                    or not PATTERN.fullmatch(m.name)
                    or m.size > 15 * 1024 * 1024
                ):
                    raise ValueError("Unsafe attachment archive")
                stream = tar.extractfile(m)
                if stream:
                    target = root / m.name
                    # Immutable UUID objects; atomic replacement, no extraction of paths.
                    temp = target.with_suffix(".restoring")
                    temp.write_bytes(stream.read())
                    temp.replace(target)
    else:
        raise SystemExit("export or restore required")


if __name__ == "__main__":
    main()
