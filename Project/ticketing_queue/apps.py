from django.apps import AppConfig


class TicketingQueueConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'   # ← add this line
    name = 'ticketing_queue'
