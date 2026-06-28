from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, model: BaseModel) -> None:
    ensure_parent_dir(path)
    path.write_text(
        model.model_dump_json(indent=2, by_alias=True) + "\n", encoding="utf-8"
    )


def read_json_model(path: Path, model_type: type[T]) -> T:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[BaseModel]) -> int:
    ensure_parent_dir(path)
    count = 0
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(row.model_dump_json(by_alias=True) + "\n")
            count += 1
    return count


def read_jsonl_model(path: Path, model_type: type[T]) -> list[T]:
    rows: list[T] = []
    with path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(model_type.model_validate_json(stripped))
            except Exception as exc:  # pragma: no cover - keeps CLI errors readable.
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def dump_json_data(path: Path, data: object) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
