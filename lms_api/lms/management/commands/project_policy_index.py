"""Project PostgreSQL policy revisions to a separate staging Pinecone namespace."""

from __future__ import annotations

import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from lms.models import PolicyDocumentRevisions, PolicyDocuments
from lms.policy_projection import records_for_revision


STAGING_NAMESPACE = "policy_postgres"


class Command(BaseCommand):
    help = "Preview or project active PostgreSQL policies to Pinecone staging namespace."

    def add_arguments(self, parser):
        parser.add_argument("--target-db", required=True, help="Exact DB_NAME to read")
        parser.add_argument("--expected-documents", type=int, help="Required with --apply")
        parser.add_argument("--apply", action="store_true", help="Call embeddings and write to Pinecone staging")

    def handle(self, *args, **options):
        actual = connections["default"].settings_dict["NAME"]
        if options["target_db"] != actual:
            raise CommandError("--target-db must match the connected DB_NAME")
        repo = Path(settings.REPO_DIR)
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))

        documents = list(PolicyDocuments.objects.filter(is_active=True).order_by("source_key"))
        if not documents:
            raise CommandError("No active PostgreSQL policy documents; import sources first")
        if options["apply"] and options["expected_documents"] != len(documents):
            raise CommandError("--apply requires --expected-documents equal to active document count")

        records = []
        for document in documents:
            revision = (PolicyDocumentRevisions.objects.filter(document=document)
                        .order_by("-revision_no").first())
            if revision is None:
                raise CommandError(f"Policy document {document.pk} has no revision")
            try:
                records.extend(records_for_revision(document, revision))
            except Exception as exc:
                raise CommandError(f"Policy document {document.pk} cannot be projected: {exc}") from exc
        ids = [record.metadata["doc_id"] for record in records]
        if len(ids) != len(set(ids)):
            raise CommandError("Duplicate Pinecone vector IDs in projection")

        self.stdout.write(f"documents={len(documents)} chunks={len(records)} namespace={STAGING_NAMESPACE}")
        if not options["apply"]:
            self.stdout.write("preview only; Pinecone unchanged")
            return

        from vectordb.policy_ingestion import MODULE_DIR, upload_records

        state_path = MODULE_DIR / ".policy_postgres_projection_state.json"
        result = upload_records(records, state_path=state_path, namespace=STAGING_NAMESPACE)
        self.stdout.write(f"upserted={result['upserted']} namespace={STAGING_NAMESPACE}")
