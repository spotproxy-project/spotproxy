import os
from django.apps import AppConfig
from assignments.services import startup


class AssignmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "assignments"

    def ready(self):
        # Your function to run on startup
        if os.environ.get("RUN_MAIN") == "FALSE":
            startup.test_startup()
