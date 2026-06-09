"""
Seed a project with demo agent runs (a scout session + a few runs and tool
calls), so the Runs/activity view has something to show before Hermes is wired.

Usage:
    python manage.py seed_research_runs --project <id>
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from research.constants import (
    AgentRunStatus,
    AgentToolCallStatus,
    ResearchSessionMode,
)
from research.models import (
    ResearchAgentRun,
    ResearchAgentToolCall,
    ResearchProject,
    ResearchSession,
)


class Command(BaseCommand):
    help = "Seed demo agent runs (a scout session) for a research project."

    def add_arguments(self, parser):
        parser.add_argument(
            "--project",
            type=int,
            required=True,
            help="ResearchProject id to seed runs into.",
        )

    def handle(self, *args, **options):
        project_id = options["project"]
        try:
            project = ResearchProject.objects.get(id=project_id)
        except ResearchProject.DoesNotExist:
            raise CommandError(f"ResearchProject {project_id} not found.")

        user = project.user
        session, _ = ResearchSession.objects.get_or_create(
            project=project,
            mode=ResearchSessionMode.SCOUT,
            is_deleted=False,
            defaults={"user": user},
        )

        now = timezone.now()

        run1 = ResearchAgentRun.objects.create(
            session=session,
            project=project,
            user=user,
            role="scout",
            mode=ResearchSessionMode.SCOUT,
            task="Flexicurity labour-market evidence and transferability",
            status=AgentRunStatus.COMPLETED,
            soul_file_version="v3",
            allowed_tools=["consensus", "web"],
            started_at=now - timedelta(days=1, seconds=68),
            completed_at=now - timedelta(days=1),
            cost="0.10",
        )
        ResearchAgentToolCall.objects.create(
            run=run1,
            tool="consensus",
            arguments={"query": "flexicurity Denmark employment security outcomes"},
            status=AgentToolCallStatus.SUCCESS,
            duration_ms=1900,
        )
        ResearchAgentToolCall.objects.create(
            run=run1,
            tool="web",
            arguments={"query": "OECD labour market security index Nordic"},
            status=AgentToolCallStatus.SUCCESS,
            duration_ms=2500,
        )

        run2 = ResearchAgentRun.objects.create(
            session=session,
            project=project,
            user=user,
            role="critic",
            mode=ResearchSessionMode.SCOUT,
            task='Pressure-test "high taxes cause Nordic growth" (claim in draft §2)',
            status=AgentRunStatus.COMPLETED,
            soul_file_version="v3",
            allowed_tools=["scite"],
            started_at=now - timedelta(hours=2, seconds=26),
            completed_at=now - timedelta(hours=2),
            cost="0.03",
        )
        ResearchAgentToolCall.objects.create(
            run=run2,
            tool="scite",
            arguments={"query": "tax rate causal growth Nordic — supporting vs disputing"},
            status=AgentToolCallStatus.SUCCESS,
            duration_ms=2200,
        )

        run3 = ResearchAgentRun.objects.create(
            session=session,
            project=project,
            user=user,
            role="scout",
            mode=ResearchSessionMode.SCOUT,
            task="Mechanisms behind Nordic intergenerational mobility",
            status=AgentRunStatus.RUNNING,
            soul_file_version="v3",
            allowed_tools=["consensus", "scite"],
            started_at=now,
        )
        ResearchAgentToolCall.objects.create(
            run=run3,
            tool="consensus",
            arguments={"query": "social trust universal services intergenerational mobility"},
            status=AgentToolCallStatus.SUCCESS,
            duration_ms=1600,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded 3 runs into project {project_id} "
                f"(session {session.id}, runs {run1.id}/{run2.id}/{run3.id})."
            )
        )
