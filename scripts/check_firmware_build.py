"""Verify the generated ESP-IDF partition table and factory app size."""

import csv
import os
from pathlib import Path
import subprocess
import sys


def main():
    build_dir = Path("firmware/build")
    decoder = Path(os.environ["IDF_PATH"]) / "components/partition_table/gen_esp32part.py"
    table = subprocess.check_output(
        [sys.executable, decoder, build_dir / "partition_table/partition-table.bin"], text=True,
    )
    print(table, end="")
    partitions = list(csv.reader(line for line in table.splitlines() if line and not line.startswith("#")))
    if partitions != [
        ["nvs", "data", "nvs", "0x9000", "24K", ""],
        ["phy_init", "data", "phy", "0xf000", "4K", ""],
        ["factory", "app", "factory", "0x10000", "4M", ""],
    ]:
        raise SystemExit("Unexpected partition table")

    capacity = 4 * 1024 * 1024
    size = (build_dir / "grokwatch.bin").stat().st_size
    print(f"grokwatch.bin: {size:,} / {capacity:,} bytes")
    if not 0 < size <= capacity:
        raise SystemExit("App size is outside the factory partition capacity")


if __name__ == "__main__":
    main()
