from django.utils import timezone

class AdminActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only track admins visiting admin/super pages, not public pages
        if (request.user.is_authenticated and 
            request.user.is_staff and
            not request.user.is_superuser and  # ← exclude superadmin
            request.path.startswith('/staff/')):
            
            from .models import AdminOnlineStatus
            AdminOnlineStatus.objects.update_or_create(
                user=request.user,
                defaults={'last_seen': timezone.now()}
            )

        return response