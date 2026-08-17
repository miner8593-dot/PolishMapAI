"""Generate a deterministic large MP map for packaged GUI smoke tests."""
from pathlib import Path
import sys


def main(path: str, count: int = 18_000) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="cp1251", newline="") as stream:
        stream.write("[IMG ID]\r\nID=1\r\n[END-IMG ID]\r\n")
        for number in range(count):
            row, column = divmod(number, 180)
            lat = 54.0 + row * 0.002; lon = 72.0 + column * 0.002
            stream.write(
                "[POI]\r\nType=0x2f00\r\nEndLevel=9\r\n"
                f"Data0=({lat:.6f},{lon:.6f})\r\n[END]\r\n"
            )


if __name__ == "__main__":
    main(sys.argv[1])
