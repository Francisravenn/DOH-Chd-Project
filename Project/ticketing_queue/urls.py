from django.urls import path
from . import views
from ticketing_queue.views import admin_logout, admin_dashboard, archive_reports

urlpatterns = [
    path('', views.user_landing, name='user_landing'),
    path('submit/', views.user_form, name='user_form'),
    path('my-tickets/', views.my_tickets, name='my_tickets'),
    path('search-ticket/', views.search_ticket, name='search_ticket'),
    path('search-ticket-api/', views.search_ticket_api, name='search_ticket_api'),

    path('ticket/<int:pk>/confirmation/', views.ticket_confirmation, name='ticket_confirmation'),
    path('staff/login/', views.admin_login, name='staff_login'),
    path('staff/dashboard/', admin_dashboard, name='staff_dashboard'),
    path('staff/ticket/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('staff/report/', views.generate_report, name='generate_report'),
    path('staff/logout/', admin_logout, name='admin_logout'),
    path('admin/ticket/<int:pk>/accept/', views.accept_ticket, name='accept_ticket'),
    path('ticket/<int:pk>/accept/', views.accept_ticket, name='accept_ticket'),
    path('ticket/<int:pk>/complete/', views.complete_ticket, name='complete_ticket'),
    path('assist-ticket/<int:pk>/', views.assist_ticket, name='assist_ticket'),
    path('live-queue/', views.live_queue, name='live_queue'),
    path('archive/', archive_reports, name='archive_reports'),
    path('ticket/<int:pk>/update/', views.update_ticket, name='update_ticket'),
    path('super/login/', views.superadmin_login, name='superadmin_login'),
    path('super/add-admin/', views.add_admin_user, name='add_admin_user'),
    path('super/dashboard/', views.superadmin_dashboard, name='super_admin_dashboard'),
    path('super/manage-users/', views.superadmin_manage_users, name='manage_users'),
    path('super/logs-audit/', views.audit_logs, name='audit_logs'),
    path('super/all-tickets/', views.all_tickets, name='all_tickets'),
    path('staff/reports/', views.reports, name='reports'),
    path('super/archive/', views.superadmin_archive, name='super_admin_archive'),
    path('ticket/<int:pk>/reopen/', views.reopen_ticket, name='reopen_ticket'),
    path('archive/ticket/<int:pk>/print/', views.archived_ticket_print, name='archived_ticket_print'),
    path('archive/save-action-taken/', views.save_action_taken, name='save_action_taken'),
    path('add-action-taken-option/', views.add_action_taken_option, name='add_action_taken_option'),
    path('super/reports/', views.superadmin_reports, name='superadmin_reports'),
    path('poll-notifications/', views.poll_notifications, name='poll_notifications'),
    path('poll-assisting/', views.poll_assisting, name='poll_assisting'),
    path('heartbeat/', views.heartbeat, name='heartbeat'),
    path('super-admin/assist/<int:pk>/', views.super_admin_assist_ticket, name='super_admin_assist_ticket'),

    
]