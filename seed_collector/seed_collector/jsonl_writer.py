import json
from pathlib import Path
from typing import Any


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fp = path.open("w", encoding="utf-8")

    def write(self, record: Any) -> None:
        json.dump(record, self._fp, ensure_ascii=True)
        self._fp.write("\n")
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()
