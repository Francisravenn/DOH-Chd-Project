from django.contrib import admin
from .models import Ticket, ITRequest, ActionTaken, AuditLog  # import ALL your models

# Basic registration (shows default list view)
admin.site.register(Ticket)
admin.site.register(ITRequest)
admin.site.register(ActionTaken)
admin.site.register(AuditLog)