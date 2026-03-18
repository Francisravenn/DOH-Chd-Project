from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

# Define the dummy view FIRST (before using it in urlpatterns)
def dummy_sw(request):
    return HttpResponse(
        """
        // Tiny dummy service worker – stops browser from probing with invalid POST /
        // (prevents fake CSRF 403 errors on localhost in Chrome/Edge)
        self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
        self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
        """.strip(),
        content_type='application/javascript'
    )

def dummy_manifest(request):
    return HttpResponse(
        '''{
          "name": "DOH IT Helpdesk Dev",
          "short_name": "DOH Dev",
          "start_url": ".",
          "display": "standalone",
          "background_color": "#ffffff",
          "theme_color": "#000000"
        }''',
        content_type='application/manifest+json'
    )

urlpatterns = [
    path('admin/', admin.site.urls),                     # Django admin

    # Your main app (ticketing_queue) – this probably handles '' (root) and other paths
    path('', include('ticketing_queue.urls')),

    # Dummy service worker endpoint – add this to silence browser probes
    path('service-worker.js', dummy_sw),

    # django-browser-reload support (good to have if you're using the package)
    # This enables auto-reload on code/template/static changes
    path('__reload__/', include('django_browser_reload.urls')),
]