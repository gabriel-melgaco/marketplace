"""
Celery application configuration for the Marketplace Academia backend.

Broker  : Redis DB 0
Results : Redis DB 0
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

app = Celery('marketplace_academia')

# Read Celery config from Django settings using the CELERY_ namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS.
app.autodiscover_tasks()
