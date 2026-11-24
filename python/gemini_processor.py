import sys
import orjson
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

# --- SCHEMA ---
class PlaceUpdate(BaseModel):
    id: str
    lang: str = "en"
    delivery_platforms: list[str] | None = None
    discount_platforms: list[str] | None = None
    rating: float | None = Field(default=None, ge=0.0, le=5.0)
    hours: dict[str, str] | None = None
    photos: list[str] | None = None

    @field_validator("delivery_platforms", "discount_platforms", "photos", mode="before")
    @classmethod
    def empty_list_to_none(cls, v: Any) -> Any:
        if isinstance(v, list) and len(v) == 0:
            return None
        return v

    @field_validator("hours", mode="before")
    @classmethod
    def empty_dict_to_none(cls, v: Any) -> Any:
        if isinstance(v, dict) and len(v) == 0:
            return None
        return v

PlaceUpdateList = TypeAdapter(list[PlaceUpdate])

# --- FAILURE LOGGER ---
def record_failure(place_id: str, lang: str, error: str, log_path: str = "failed_places.jsonl") -> None:
    entry = {
        "id": place_id,
        "lang": lang,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(log_path, "ab") as f:
        f.write(orjson.dumps(entry) + b"\n")

# --- MERGE LOGIC ---
def upsert_place(db: dict[str, dict[str, Any]], update: PlaceUpdate, prefer_existing: bool = True) -> dict[str, Any]:
    existing = db.get(update.id, {})
    incoming = update.model_dump(exclude_none=True, exclude_unset=True)

    if not existing:
        db[update.id] = incoming
        return db[update.id]

    for key, new_val in incoming.items():
        current_val = existing.get(key)
        is_current_empty = current_val is None or current_val == [] or current_val == {}
        if is_current_empty or not prefer_existing:
            existing[key] = new_val

    db[update.id] = existing
    return existing

# --- MAIN BATCH PROCESSOR ---
def process_gemini_batch(raw_json_bytes: bytes, db: dict[str, dict[str, Any]]) -> None:
    try:
        updates = PlaceUpdateList.validate_json(raw_json_bytes)
    except ValidationError as e:
        record_failure("BATCH_LEVEL", "unknown", e.json())
        return

    for item in updates:
        try:
            upsert_place(db, item, prefer_existing=True)
        except Exception as exc:
            record_failure(item.id, item.lang, str(exc))

# --- CLI ENTRYPOINT ---
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python gemini_processor.py <gemini_output.json> <local_db.json>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    db_path = Path(sys.argv[2])

    # Load existing DB or init empty
    db = orjson.loads(db_path.read_bytes()) if db_path.exists() else {}
    
    # Process
    process_gemini_batch(input_path.read_bytes(), db)
    
    # Save back
    db_path.write_bytes(orjson.dumps(db, option=orjson.OPT_INDENT_2))
    print(f"Processed. Wrote {len(db)} records to {db_path}")