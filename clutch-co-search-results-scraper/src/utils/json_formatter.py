import json
import logging
from pathlib import Path
from typing import Any, Iterable, List, Dict

logger = logging.getLogger("json_formatter")

def ensure_serializable(data: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure that all values are JSON-serializable by converting unknown
    types to strings. This makes the output robust against edge cases.
    """
    sanitized: List[Dict[str, Any]] = []

    for item in data:
        clean_item: Dict[str, Any] = {}
        for key, value in item.items():
            try:
                json.dumps(value)
                clean_item[key] = value
            except TypeError:
                clean_item[key] = str(value)
        sanitized.append(clean_item)

    return sanitized

def save_json(data: Iterable[Dict[str, Any]], output_path: Path, pretty: bool = True) -> None:
    """
    Save a list of dictionaries to a JSON file, creating parent directories
    if necessary.
    """
    output_path = Path(output_path)
    if not output_path.parent.exists():
        logger.debug(f"Creating parent directory for output: {output_path.parent}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

    serializable_data = ensure_serializable(list(data))

    try:
        with output_path.open("w", encoding="utf-8") as f:
            if pretty:
                json.dump(serializable_data, f, indent=4, ensure_ascii=False)
            else:
                json.dump(serializable_data, f, separators=(",", ":"), ensure_ascii=False)
        logger.info(f"Saved {len(serializable_data)} records to {output_path}")
    except Exception as exc:
        logger.exception(f"Failed to write JSON to {output_path}: {exc}")
        raise