from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import (
    AgentOutput,
    Artifact,
    Evidence,
    KnowledgeAsset,
    Run,
    RunStatus,
    Task,
    TaskDependency,
    TaskStatus,
    utcnow,
)
from app.safety import DISCLAIMER, apply_output_guardrails


@dataclass(frozen=True)
class TaskBlueprint:
    kind: str
    agent_name: str
    title: str
    depends_on: tuple[str, ...] = ()


TASK_BLUEPRINTS = (
    TaskBlueprint("content_discovery", "Content Discovery Agent", "Index seed knowledge"),
    TaskBlueprint("osint", "OSINT Agent", "Compile area signal board"),
    TaskBlueprint("cre", "CRE Agent", "Define site and lease criteria"),
    TaskBlueprint("compliance", "Compliance Agent", "Draft compliance and licensing map"),
    TaskBlueprint(
        "strategy",
        "Strategy Agent",
        "Synthesize go-to-market recommendation",
        ("content_discovery", "osint", "cre", "compliance"),
    ),
    TaskBlueprint("executive_brief", "Orchestrator Agent", "Generate executive brief", ("strategy",)),
    TaskBlueprint("launch_roadmap", "Orchestrator Agent", "Generate launch roadmap", ("strategy",)),
    TaskBlueprint("launch_checklist", "Orchestrator Agent", "Generate launch checklist", ("strategy",)),
)


def create_run(
    session: Session,
    settings: Settings,
    area: str,
    notes: str = "",
    idempotency_key: str | None = None,
) -> Run:
    if idempotency_key:
        existing = session.execute(select(Run).where(Run.idempotency_key == idempotency_key)).scalar_one_or_none()
        if existing is not None:
            return existing

    run = Run(area=area.strip(), notes=notes.strip(), idempotency_key=idempotency_key, status=RunStatus.queued.value)
    session.add(run)
    session.flush()

    tasks_by_kind: dict[str, Task] = {}
    for blueprint in TASK_BLUEPRINTS:
        task = Task(
            run_id=run.id,
            kind=blueprint.kind,
            title=blueprint.title,
            agent_name=blueprint.agent_name,
            status=TaskStatus.queued.value if not blueprint.depends_on else TaskStatus.blocked.value,
            task_key=f"{run.id}:{blueprint.kind}",
            max_attempts=settings.max_task_retries + 1,
        )
        session.add(task)
        session.flush()
        tasks_by_kind[blueprint.kind] = task

    for blueprint in TASK_BLUEPRINTS:
        task = tasks_by_kind[blueprint.kind]
        for dependency_kind in blueprint.depends_on:
            session.add(TaskDependency(task_id=task.id, depends_on_task_id=tasks_by_kind[dependency_kind].id))

    session.commit()
    return session.get(Run, run.id)


def process_next_task(session_factory: sessionmaker, settings: Settings) -> bool:
    with session_factory() as session:
        refresh_blocked_tasks(session)
        task = session.execute(
            select(Task)
            .where(Task.status == TaskStatus.queued.value)
            .order_by(Task.created_at.asc(), Task.id.asc())
        ).scalars().first()
        if task is None:
            finalize_runs(session)
            return False

        task.status = TaskStatus.running.value
        task.attempt_count += 1
        task.started_at = task.started_at or utcnow()
        run = session.get(Run, task.run_id)
        if run and run.status == RunStatus.queued.value:
            run.status = RunStatus.running.value
            run.started_at = run.started_at or utcnow()
        session.commit()
        task_id = task.id

    try:
        with session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                return False
            execute_task(session, task)
            task.status = TaskStatus.done.value
            task.completed_at = utcnow()
            task.last_error = None
            refresh_blocked_tasks(session, task.run_id)
            finalize_runs(session, task.run_id)
            session.commit()
            return True
    except (RuntimeError, ValueError) as exc:  # pragma: no cover - exercised via status assertions
        with session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                return False
            task.last_error = str(exc)
            if task.attempt_count < task.max_attempts:
                task.status = TaskStatus.queued.value
            else:
                task.status = TaskStatus.failed.value
                task.completed_at = utcnow()
            finalize_runs(session, task.run_id)
            session.commit()
        return True


def process_run_until_complete(
    session_factory: sessionmaker,
    settings: Settings,
    run_id: str,
    max_steps: int = 50,
) -> Run:
    for _ in range(max_steps):
        processed = process_next_task(session_factory, settings)
        with session_factory() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise ValueError(f"Run {run_id} not found")
            if run.status in {RunStatus.completed.value, RunStatus.failed.value}:
                return run
        if not processed:
            break
    with session_factory() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        return run


def refresh_blocked_tasks(session: Session, run_id: str | None = None) -> None:
    query = select(Task).where(Task.status == TaskStatus.blocked.value)
    if run_id:
        query = query.where(Task.run_id == run_id)
    blocked_tasks = session.execute(query).scalars().all()
    for task in blocked_tasks:
        dependency_ids = [dependency.depends_on_task_id for dependency in task.dependencies]
        dependencies = session.execute(select(Task).where(Task.id.in_(dependency_ids))).scalars().all()
        if dependencies and all(dep.status == TaskStatus.done.value for dep in dependencies):
            task.status = TaskStatus.queued.value
    session.flush()


def finalize_runs(session: Session, run_id: str | None = None) -> None:
    query = select(Run)
    if run_id:
        query = query.where(Run.id == run_id)
    runs = session.execute(query).scalars().all()
    for run in runs:
        statuses = [task.status for task in run.tasks]
        if statuses and all(status == TaskStatus.done.value for status in statuses):
            run.status = RunStatus.completed.value
            run.completed_at = utcnow()
        elif any(status == TaskStatus.failed.value for status in statuses):
            run.status = RunStatus.failed.value
            run.completed_at = utcnow()
        elif any(status in {TaskStatus.running.value, TaskStatus.done.value, TaskStatus.queued.value} for status in statuses):
            run.status = RunStatus.running.value
    session.flush()


def execute_task(session: Session, task: Task) -> None:
    handlers = {
        "content_discovery": build_content_discovery,
        "osint": build_osint_output,
        "cre": build_cre_output,
        "compliance": build_compliance_output,
        "strategy": build_strategy_output,
        "executive_brief": build_executive_brief,
        "launch_roadmap": build_launch_roadmap,
        "launch_checklist": build_launch_checklist,
    }
    handlers[task.kind](session, task)


def replace_task_output(session: Session, task: Task, title: str, output_type: str, content: str) -> AgentOutput:
    safe_content, flags = apply_output_guardrails(content)
    existing = session.execute(
        select(AgentOutput).where(AgentOutput.task_id == task.id, AgentOutput.output_type == output_type)
    ).scalar_one_or_none()
    if existing is None:
        existing = AgentOutput(
            run_id=task.run_id,
            task_id=task.id,
            title=title,
            output_type=output_type,
            content=safe_content,
            safety_flags=flags,
        )
        session.add(existing)
    else:
        existing.title = title
        existing.content = safe_content
        existing.safety_flags = flags
    session.flush()
    return existing


def replace_artifact(session: Session, task: Task, artifact_type: str, title: str, content: str) -> Artifact:
    safe_content, _ = apply_output_guardrails(content)
    artifact = session.execute(
        select(Artifact).where(Artifact.run_id == task.run_id, Artifact.artifact_type == artifact_type)
    ).scalar_one_or_none()
    if artifact is None:
        artifact = Artifact(run_id=task.run_id, artifact_type=artifact_type, title=title, content=safe_content)
        session.add(artifact)
    else:
        artifact.title = title
        artifact.content = safe_content
    session.flush()
    return artifact


def attach_evidence(
    session: Session,
    run_id: str,
    title: str,
    source_type: str,
    source_uri: str,
    citation: str,
    excerpt: str,
    task_id: int | None = None,
    artifact_id: int | None = None,
    knowledge_asset_id: int | None = None,
) -> None:
    exists = session.execute(
        select(Evidence).where(
            Evidence.run_id == run_id,
            Evidence.task_id == task_id,
            Evidence.artifact_id == artifact_id,
            Evidence.title == title,
            Evidence.source_uri == source_uri,
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(
            Evidence(
                run_id=run_id,
                task_id=task_id,
                artifact_id=artifact_id,
                knowledge_asset_id=knowledge_asset_id,
                source_type=source_type,
                title=title,
                source_uri=source_uri,
                citation=citation,
                excerpt=excerpt,
            )
        )


def ranked_assets(session: Session, area: str) -> list[KnowledgeAsset]:
    assets = session.execute(select(KnowledgeAsset).order_by(KnowledgeAsset.source_path)).scalars().all()
    tokens = {token.lower().strip(",") for token in area.split() if token.strip()}
    scored: list[tuple[int, KnowledgeAsset]] = []
    for asset in assets:
        searchable = f"{asset.title} {asset.summary} {asset.body}".lower()
        score = sum(token in searchable for token in tokens)
        scored.append((score, asset))
    return [asset for _, asset in sorted(scored, key=lambda item: (-item[0], item[1].source_path))]


def find_outputs_by_kind(session: Session, run_id: str, kinds: Iterable[str]) -> dict[str, AgentOutput]:
    outputs = session.execute(
        select(AgentOutput, Task.kind)
        .join(Task, Task.id == AgentOutput.task_id)
        .where(Task.run_id == run_id, Task.kind.in_(tuple(kinds)))
    ).all()
    return {kind: output for output, kind in outputs}


def build_content_discovery(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    assets = ranked_assets(session, run.area)[:6]
    lines = [f"# Seed knowledge for {run.area}", ""]
    for asset in assets:
        lines.append(f"- **{asset.title}** — {asset.summary}")
        attach_evidence(
            session,
            task.run_id,
            title=asset.title,
            source_type="knowledge",
            source_uri=asset.source_path,
            citation=f"Seed knowledge asset: {asset.title}",
            excerpt=asset.summary,
            task_id=task.id,
            knowledge_asset_id=asset.id,
        )
    lines.extend(
        [
            "",
            "Use these documents as attachable evidence for downstream outputs and operator review.",
        ]
    )
    replace_task_output(session, task, "Knowledge discovery summary", "knowledge_summary", "\n".join(lines))


def build_osint_output(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    content = f"""# OSINT coverage for {run.area}

## Signal board
- Identify direct wellness, recovery, chiropractic, aesthetic, and co-working competitors in {run.area}.
- Review local review platforms, business directories, and social channels for demand, complaints, and pricing anchors.
- Capture foot-traffic, parking, transit, and anchor-tenant signals for candidate corridors.

## Evidence protocol
- Record each claim with a link, screenshot, or seed document citation before it is promoted into strategy outputs.
- Keep wellness positioning separate from medical or cosmetic procedure recommendations.

## Operator follow-ups
- Validate website and listing data freshness before external outreach.
- Queue missing research as explicit tasks instead of assuming facts.
"""
    replace_task_output(session, task, "OSINT summary", "osint_summary", content)


def build_cre_output(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    content = f"""# CRE criteria for {run.area}

| Category | Target |
| --- | --- |
| Footprint | 2,000–3,000 square feet with clear circulation for fire + ice, consultation, and co-op member flow |
| Power / MEP | Sufficient electrical capacity, drainage review, HVAC zoning, and room for hot/cold equipment loads |
| Visibility | Street-facing signage, simple ingress/egress, and adjacent wellness-compatible traffic generators |
| Lease terms | Improvement allowance, exclusivity review, use clause review, and termination rights tied to approvals |

## Site diligence
1. Validate zoning and use permissions before LOI.
2. Confirm landlord flexibility for branded wellness build-out.
3. Stage a landlord/vendor RFP checklist before design lock.
"""
    replace_task_output(session, task, "CRE summary", "cre_summary", content)


def build_compliance_output(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    maryland_specific = "maryland" in run.area.lower()
    jurisdiction_note = (
        "Prioritize the Maryland compliance register and local county occupancy review."
        if maryland_specific
        else "Map the local state, county, and municipal compliance requirements before lease commitment."
    )
    content = f"""# Compliance plan for {run.area}

- {jurisdiction_note}
- Treat all service descriptions as wellness planning content until reviewed by licensed counsel and clinical advisors.
- Separate consumer marketing, consent language, sanitation controls, and incident response documentation.

## Required workstreams
1. Business registration, tax setup, insurance, and occupancy approvals.
2. Vendor SOP review for hot/cold contrast, member intake, and sanitation logging.
3. Advertising review to avoid unsupported medical or cosmetic claims.
"""
    replace_task_output(session, task, "Compliance summary", "compliance_summary", content)


def build_strategy_output(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    outputs = find_outputs_by_kind(session, task.run_id, ("content_discovery", "osint", "cre", "compliance"))
    content = f"""# Expansion recommendation for {run.area}

## Thesis
Launch a planning sprint for VYTAL COSMO CoOp — Maryland Fire + Ice in {run.area} with evidence-backed discovery, site screening, and compliance gating before capital commitments.

## Why this run is actionable
- Knowledge assets have been indexed and can be attached directly to downstream outputs.
- Market, site, and compliance tracks are decomposed into explicit operators tasks with status visibility.
- The workflow is deterministic, retryable, and audit-friendly.

## Recommended next steps
1. Score top submarkets and corridors against the CRE criteria.
2. Convert OSINT findings into a partner-ready executive brief.
3. Run compliance review before finalizing service mix or claims language.

## Source digest
- Knowledge: {outputs.get("content_discovery").title if outputs.get("content_discovery") else "Seed knowledge"}
- OSINT: {outputs.get("osint").title if outputs.get("osint") else "Area signal board"}
- CRE: {outputs.get("cre").title if outputs.get("cre") else "Site criteria"}
- Compliance: {outputs.get("compliance").title if outputs.get("compliance") else "Compliance plan"}
"""
    replace_task_output(session, task, "Strategy synthesis", "strategy_summary", content)


def build_executive_brief(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    strategy_output = find_outputs_by_kind(session, task.run_id, ("strategy",)).get("strategy")
    content = f"""# Executive Brief — {run.area}

## Opportunity
Use a gated, evidence-backed launch workflow to assess whether {run.area} can support a VYTAL COSMO CoOp wellness concept focused on fire + ice rituals and community programming.

## What the platform generated
- Deterministic task graph across OSINT, CRE, compliance, and strategy.
- Persistent outputs, citations, and knowledge attachments for auditability.
- Ready-to-export roadmap and checklist artifacts.

## Recommendation
Proceed to corridor scoring, landlord outreach preparation, and formal compliance review only after the queued evidence tasks are complete.

## Strategy context
{strategy_output.content if strategy_output else "Strategy synthesis pending."}
"""
    artifact = replace_artifact(session, task, "executive_brief", f"Executive Brief — {run.area}", content)
    attach_seed_artifact_evidence(session, task, artifact, ("01_", "02_", "05_"))


def build_launch_roadmap(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    content = f"""# 180-Day Launch Roadmap — {run.area}

## Days 0-30
- Finalize research scope, operating assumptions, and evidence capture standards.
- Rank submarkets and shortlist candidate sites.

## Days 31-90
- Run landlord/site diligence, vendor discovery, and compliance gating.
- Build the data room, owner tracker, and claims review log.

## Days 91-180
- Lock launch checklist, staffing plan, and content calendar.
- Prepare community onboarding, member journey controls, and soft-launch reviews.
"""
    artifact = replace_artifact(session, task, "launch_roadmap", f"180-Day Roadmap — {run.area}", content)
    attach_seed_artifact_evidence(session, task, artifact, ("06_", "04_", "09_"))


def build_launch_checklist(session: Session, task: Task) -> None:
    run = session.get(Run, task.run_id)
    content = f"""# Launch Checklist — {run.area}

- [ ] Confirm area input, budget assumptions, and success criteria.
- [ ] Attach all relevant knowledge assets and area-specific evidence.
- [ ] Complete CRE, compliance, and vendor diligence.
- [ ] Review claims, disclaimers, and member journey controls.
- [ ] Approve roadmap, owners, and launch readiness gate.
"""
    artifact = replace_artifact(session, task, "launch_checklist", f"Launch Checklist — {run.area}", content)
    attach_seed_artifact_evidence(session, task, artifact, ("07_", "08_", "09_"))


def attach_seed_artifact_evidence(session: Session, task: Task, artifact: Artifact, prefixes: tuple[str, ...]) -> None:
    assets = session.execute(select(KnowledgeAsset).order_by(KnowledgeAsset.source_path)).scalars().all()
    for asset in assets:
        if any(path_part in asset.source_path for path_part in prefixes):
            attach_evidence(
                session,
                task.run_id,
                title=asset.title,
                source_type="knowledge",
                source_uri=asset.source_path,
                citation=f"Attached seed evidence for {artifact.title}",
                excerpt=asset.summary,
                task_id=task.id,
                artifact_id=artifact.id,
                knowledge_asset_id=asset.id,
            )


def summarize_run_counts(run: Run) -> dict[str, int]:
    return dict(Counter(task.status for task in run.tasks))


def advisory_summary() -> str:
    return DISCLAIMER
