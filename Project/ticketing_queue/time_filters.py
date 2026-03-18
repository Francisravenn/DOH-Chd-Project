from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def minutes_since(value):
    """Returns number of minutes since the given datetime (or 0 if None)."""
    if not value:
        return 0
    delta = timezone.now() - value
    return int(delta.total_seconds() // 60)