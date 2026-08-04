from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeAsset


SEED_FILE_ORDER = [
    "00_README_START_HERE.md",
    "01_Executive_One_Pager.md",
    "02_Business_Plan.md",
    "03_Facility_Program_2500SF.md",
    "04_CoOp_Governance_RASCI.md",
    "05_Maryland_Compliance_Register.md",
    "06_180_Day_Launch_Roadmap.md",
    "07_Vendor_RFP_Checklist.md",
    "08_Member_Journey_Controls.md",
    "09_Data_Room_Index.md",
]


def slugify(filename: str) -> str:
    return filename.lower().replace(".md", "").replace("_", "-")


def summarize_markdown(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:280]
    return body.strip()[:280]


def seed_knowledge_assets(session: Session, knowledge_dir: Path) -> int:
    created_or_updated = 0
    for name in SEED_FILE_ORDER:
        path = knowledge_dir / name
        if not path.exists():
            continue

        body = path.read_text(encoding="utf-8")
        asset = session.execute(
            select(KnowledgeAsset).where(KnowledgeAsset.source_path == str(path))
        ).scalar_one_or_none()
        if asset is None:
            asset = KnowledgeAsset(
                slug=slugify(name),
                title=name.replace(".md", "").replace("_", " "),
                source_path=str(path),
                body=body,
                summary=summarize_markdown(body),
            )
            session.add(asset)
        else:
            asset.body = body
            asset.summary = summarize_markdown(body)
        created_or_updated += 1
    session.commit()
    return created_or_updated


def search_knowledge_assets(session: Session, query: str | None = None) -> list[KnowledgeAsset]:
    assets = session.execute(select(KnowledgeAsset).order_by(KnowledgeAsset.source_path)).scalars().all()
    if not query:
        return assets

    needle = query.lower()
    return [
        asset
        for asset in assets
        if needle in asset.title.lower() or needle in asset.summary.lower() or needle in asset.body.lower()
    ]
