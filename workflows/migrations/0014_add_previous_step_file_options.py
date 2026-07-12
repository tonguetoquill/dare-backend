# Generated manually for workflow file inheritance feature
#
# NOTE: This migration duplicated 0014_step_use_previous_step_embeddings_and_more
# (both added the same two fields to Step), which made every fresh install crash
# with "column use_previous_step_files already exists". The operations are now
# empty; the file itself must remain because 0015_merge_20250803_0348 depends on
# it by name.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('workflows', '0013_workflowstepsnippet'),
    ]

    operations = []
