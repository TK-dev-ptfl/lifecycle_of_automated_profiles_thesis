from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from app.auth.utils import get_current_user

router = APIRouter(prefix="/api/algorithms", tags=["algorithms"])

METHODS_ROOT = Path(__file__).resolve().parent.parent / "algorithm" / "methods"


@router.get("/method-files")
async def list_method_files(_: str = Depends(get_current_user)):
    if not METHODS_ROOT.exists():
        raise HTTPException(status_code=404, detail="Methods folder not found")

    result: dict[str, list[dict[str, str]]] = {}
    for method_dir in sorted(METHODS_ROOT.iterdir()):
        if not method_dir.is_dir():
            continue
        files: list[dict[str, str]] = []
        for file_path in sorted(method_dir.glob("*.py")):
            files.append(
                {
                    "name": file_path.name,
                    "path": str(file_path.relative_to(METHODS_ROOT)).replace("\\", "/"),
                    "content": file_path.read_text(encoding="utf-8"),
                }
            )
        result[method_dir.name] = files
    return result

