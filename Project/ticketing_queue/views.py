from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout, authenticate, login
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Count, Case, When, Value, IntegerField
from django.template.defaultfilters import timesince
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_POST
from datetime import timedelta
from django.urls import reverse
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from django.views.decorators.http import require_http_methods
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from .models import StaffProfile
from django.db.models import Q
from django.db.models import F, ExpressionWrapper, DurationField, Avg
from django.db.models.functions import Extract
from django.db.models.functions import Coalesce
from .models import ActionTakenOption
from django.contrib.auth.decorators import login_required

from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from datetime import datetime
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4



from django.db.models import Count, Avg
import csv
import json

from .models import AuditLog, Ticket, User
from .forms import TicketForm, ActionTakenForm
from .models import Ticket, ActionTaken, AuditLog, ArchivedTicket 


# USER SIDE ALL

# In views.py, replace your user_form view with this:

def user_form(request):
    print("=== user_form view called ===")
    print("Method:", request.method)
    
    if request.method == 'POST':
        print("POST DATA:", dict(request.POST))
        form = TicketForm(request.POST)
        
        if form.is_valid():
            print("Form VALID → saving...")
            ticket = form.save(commit=False)
            
            try:
                mm = int(form.cleaned_data['date_mm'])
                dd = int(form.cleaned_data['date_dd'])
                yyyy = int(form.cleaned_data['date_yyyy'])
                ticket.date_request = timezone.datetime(yyyy, mm, dd).date()
                
                hour, minute = map(int, form.cleaned_data['time'].split(':'))
                if form.cleaned_data['ampm'] == 'PM' and hour != 12:
                    hour += 12
                elif form.cleaned_data['ampm'] == 'AM' and hour == 12:
                    hour = 0
                ticket.time_request = timezone.datetime(2000, 1, 1, hour, minute).time()
                ticket.am_pm = form.cleaned_data['ampm']
            except Exception as e:
                print("Date/time parse failed:", str(e))
                now = timezone.now()
                ticket.date_request = now.date()
                ticket.time_request = now.time()
                ticket.am_pm = 'AM' if now.hour < 12 else 'PM'

            ticket.clean()

            if not ticket.control_no:
                ticket.generate_control_no()
                print("Generated control_no:", ticket.control_no)

            ticket.status = 'pending'   
            ticket.save()

            AuditLog.objects.create(
                action='created ticket',
                details=f'Ticket {ticket.control_no} created by {ticket.requested_by} from IP {get_client_ip(request)}',
                ticket=ticket,
                ip_address=get_client_ip(request)
            )

            messages.info(
                request,
                f"New IT request submitted! Control No: {ticket.control_no}",
                extra_tags='new_ticket'
            )

            # ── AJAX request → return JSON ──
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'control_no': ticket.control_no,
                    'ticket_data': {
                        'control_no':          ticket.control_no,
                        'date_request':        ticket.date_request.strftime('%m/%d/%Y') if ticket.date_request else '',
                        'time_request':        ticket.time_request.strftime('%I:%M') if ticket.time_request else '',
                        'am_pm':               ticket.am_pm or '',
                        'request_complaint':   ticket.request_complaint or '',
                        'equipment':           ticket.equipment or '',
                        'brand':               ticket.brand or '',
                        'model':               ticket.model or '',
                        'department_division': ticket.department_division or '',
                        'section_unit':        ticket.section_unit or '',
                        'is_urgent':           ticket.is_urgent,
                        'requested_by':        ticket.requested_by or '',
                    }
                })

            # Normal request → redirect
            return redirect('ticket_confirmation', pk=ticket.pk)
        
        else:
            print("FORM INVALID. ERRORS:", form.errors.as_json())
            # ── AJAX request with errors → return JSON ──
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors.as_json(),
                })
    
    else:
        print("GET request – showing empty form")
        form = TicketForm()

    return render(request, 'user_form.html', {'form': form})



def user_landing(request):
    """Landing page for users — choose to submit, view, or search tickets."""
    return render(request, 'user_landing.html')


def my_tickets(request):
    """Show all tickets submitted by a given name (from session or query param)."""
    requested_by = request.GET.get('name', '').strip()
    tickets = []

    if requested_by:
        tickets = Ticket.objects.filter(
            requested_by__iexact=requested_by
        ).order_by('-created_at')

    return render(request, 'my_tickets.html', {
        'tickets': tickets,
        'requested_by': requested_by,
    })


def search_ticket(request):
    """Search for a ticket by control number."""
    control_no = request.GET.get('control_no', '').strip()
    ticket = None
    search_error = None

    if control_no:
        ticket = Ticket.objects.filter(control_no__iexact=control_no).first()
        if not ticket:
            # also try archived
            ticket = ArchivedTicket.objects.filter(control_no__iexact=control_no).first()
        if not ticket:
            search_error = f'No ticket found with ID "{control_no}". Please check and try again.'

    return render(request, 'search_ticket.html', {
        'ticket': ticket,
        'control_no': control_no,
        'search_error': search_error,
    })


def search_ticket_api(request):
    """AJAX endpoint — searches by Control No OR requester name. Returns JSON for modal."""
    query = request.GET.get('control_no', '').strip()

    if not query:
        return JsonResponse({'found': False, 'query': query})

    def format_ticket(ticket):
        date_str = ticket.date_request.strftime('%B %d, %Y') if ticket.date_request else 'N/A'
        time_str = ticket.time_request.strftime('%I:%M') if ticket.time_request else ''
        ampm_str = ticket.am_pm or ''
        completed_str = ticket.completed_at.strftime('%B %d, %Y %I:%M %p') if ticket.completed_at else ''
        assisted_by_str = ''
        if ticket.assisted_by:
            full = ticket.assisted_by.get_full_name()
            assisted_by_str = full if full else ticket.assisted_by.username
        return {
            'control_no':          ticket.control_no,
            'status':              ticket.status,
            'requested_by':        ticket.requested_by or 'N/A',
            'date_request':        date_str,
            'time_request':        time_str,
            'am_pm':               ampm_str,
            'department_division': ticket.department_division or '',
            'section_unit':        ticket.section_unit or '',
            'request_complaint':   ticket.request_complaint or '',
            'equipment':           ticket.equipment or '',
            'brand':               ticket.brand or '',
            'model':               ticket.model or '',
            'is_urgent':           ticket.is_urgent,
            'assisted_by':         assisted_by_str,
            'completed_at':        completed_str,
        }

    # 1. Try exact control number match first
    ticket = Ticket.objects.filter(control_no__iexact=query).first()
    if ticket:
        return JsonResponse({'found': True, 'ticket': format_ticket(ticket)})

    # 2. Try name search (contains, case-insensitive) — latest first
    tickets_by_name = Ticket.objects.filter(
        requested_by__iexact=query
    ).order_by('-created_at')

    if tickets_by_name.exists():
        active_statuses = ['pending', 'accepted', 'assisting']
        active_count = tickets_by_name.filter(status__in=active_statuses).count()
        return JsonResponse({
            'found':        True,
            'tickets':      [format_ticket(t) for t in tickets_by_name],
            'has_active':   active_count > 0,
            'active_count': active_count,
            'query':        query,
        })

    # 3. Nothing found
    return JsonResponse({'found': False, 'query': query})


def ticket_confirmation(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    return render(request, 'ticket_confirmation.html', {
        'ticket': ticket,
        'message': "Your IT job request has been successfully submitted.",
    })




# ADMIN SIDE ALL
#admin part


def admin_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            AuditLog.objects.create(
                user=user,
                action='login',
                details=f'{user.username} logged in from IP {get_client_ip(request)}',
                ip_address=get_client_ip(request)
            )

            return redirect('staff_dashboard')
    else:
        form = AuthenticationForm()

    form.fields['username'].widget.attrs.update({'class': 'form-control'})
    form.fields['password'].widget.attrs.update({'class': 'form-control'})

    return render(request, 'admin_login.html', {'form': form})


@login_required
def admin_dashboard(request):
    all_tickets = Ticket.objects.all()

    def get_ordered_qs(qs):
        return qs.annotate(
            urgency_priority=Case(
                When(is_urgent=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        ).order_by('-urgency_priority', 'created_at')

    # Time thresholds
    seven_days_ago = timezone.now() - timedelta(days=7)
    missing_threshold = timezone.now() - timedelta(hours=24)

    # New Request tab: pending + accepted (unassigned) → they stay here until assigned
    new_tickets = all_tickets.filter(
        status__in=['pending', 'accepted']
    ).annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-urgency_priority', '-created_at')

    # Missing / Overdue tab (updated for consistency)
    missing_tickets = all_tickets.filter(
        status__in=['pending', 'accepted'],
        created_at__lt=missing_threshold
    ).annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('created_at')

    # Accepted tab now shows only "being assisted" tickets
    accepted_tickets = get_ordered_qs(all_tickets.filter(status='assisting'))

    completed_tickets = get_ordered_qs(
        all_tickets.filter(
            status='completed',
            completed_at__gte=seven_days_ago
        )
    )

    context = {
        # Stat cards
        'new_count': new_tickets.count(),                   
        'assisting_count': all_tickets.filter(status='assisting').count(),
        'completed_count': completed_tickets.count(),
        'missing_tasks_count': missing_tickets.count(),

        # Tab querysets
        'pending_tickets': new_tickets,          
        'accepted_tickets': accepted_tickets,   
        'completed_tickets': completed_tickets,
        'missing_tickets': missing_tickets,

        'staff_users': User.objects.filter(
            username__in=['Morro', 'Rich', 'Tim']
        ).order_by('username'),

        'tab': request.GET.get('tab', 'new'),
        'assisting_tickets': accepted_tickets,
    }

    return render(request, 'admin_dashboard.html', context)


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    action_instance = ActionTaken.objects.filter(ticket=ticket).first()

    if request.method == 'POST':
        form = ActionTakenForm(request.POST, instance=action_instance)
        if form.is_valid():
            action = form.save(commit=False)
            action.ticket = ticket
            action.save()

            ticket.status = 'completed'
            ticket.completed_at = timezone.now()
            ticket.save()

            # Archive instantly
            archived = ArchivedTicket.objects.create(
                control_no       = ticket.control_no,
                requested_by     = ticket.requested_by,
                division         = ticket.department_division or ticket.section_unit or "N/A",  # copy from new fields in Ticket
                description      = ticket.request_complaint,
                is_urgent        = ticket.is_urgent,
                created_at       = ticket.created_at,
                completed_at     = ticket.completed_at,
            )

            AuditLog.objects.create(
                user=request.user,
                action='completed ticket',
                details=f'Ticket {ticket.control_no} marked as completed by {request.user.username} from IP {get_client_ip(request)}',  # ← CHANGE THIS line
                ip_address=get_client_ip(request)  
            )
            return redirect('admin_dashboard')
    else:
        form = ActionTakenForm(instance=action_instance)

    return render(request, 'ticket_detail.html', {
        'ticket': ticket,
        'form': form,
    })


@login_required
def accept_ticket(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        if ticket.status != 'pending':
            messages.warning(request, f"Cannot accept ticket {ticket.control_no} — status is '{ticket.status}'.")
            return redirect('staff_dashboard')
        
        
        ticket.status = 'accepted'
        ticket.save()
        messages.success(request, f"Ticket {ticket.control_no} accepted successfully!")

        AuditLog.objects.create(
            user=request.user,
            action='accepted ticket',
            details=f'Ticket {ticket.control_no} accepted by {request.user.username}',
            ticket=ticket,
            ip_address=get_client_ip(request)
        )

    current_tab = request.POST.get('tab', 'new')
    return redirect(f"{reverse('staff_dashboard')}?tab={current_tab}")


@login_required
def assist_ticket(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        if ticket.status != 'accepted':
            messages.warning(request, f"Cannot assist — status is {ticket.status}")
            return redirect('staff_dashboard')

        assisted_by_id = request.POST.get('assisted_by')
        if not assisted_by_id:
            messages.error(request, "No staff selected.")
            return redirect('staff_dashboard')

        try:
            assisted_user = User.objects.get(id=assisted_by_id)
        except User.DoesNotExist:
            messages.error(request, "Staff not found.")
            return redirect('staff_dashboard')

        ticket.status = 'assisting'
        ticket.assisted_by = assisted_user
        ticket.save()

        messages.success(request, f"Ticket {ticket.control_no} assigned to {assisted_user.username}")

        AuditLog.objects.create(
            user=request.user,
            action='assisting ticket',
            details=f'Ticket {ticket.control_no} assigned to {assisted_user.username} by {request.user.username}',
            ticket=ticket,
            ip_address=get_client_ip(request)
        )
    
        current_tab = request.POST.get('tab', 'new')
    return redirect(f"{reverse('staff_dashboard')}?tab={current_tab}")


@login_required
def complete_ticket(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        
        current_tab = request.POST.get('tab', 'accepted')
        
        if ticket.status != 'assisting':
            messages.warning(request, f"Cannot complete ticket {ticket.control_no} — status is '{ticket.status}'.")
            if request.POST.get('from_super_admin') or request.user.is_superuser:
                return redirect(f"{reverse('super_admin_dashboard')}?tab={current_tab}")
            return redirect(f"{reverse('staff_dashboard')}?tab={current_tab}")
        
        now = timezone.now()
        ticket.status = 'completed'
        ticket.completed_at = now
        ticket.save()

        completed_by = ticket.assisted_by if ticket.assisted_by else request.user

        AuditLog.objects.create(
            user=completed_by,
            action='completed ticket',
            details=f'Ticket {ticket.control_no} completed by {completed_by.username}',
            ticket=ticket,
            ip_address=get_client_ip(request)
        )
        
        # Archive - make it very robust
        try:
            completed_by_user = ticket.assisted_by if ticket.assisted_by else request.user  # who really finished it

            if not ArchivedTicket.objects.filter(control_no=ticket.control_no).exists():
                ArchivedTicket.objects.create(
                    control_no       = ticket.control_no,
                    requested_by     = ticket.requested_by or "Unknown",
                    division         = ticket.department_division or ticket.section_unit or "N/A",
                    description      = ticket.request_complaint or "(no description)",
                    is_urgent        = ticket.is_urgent,
                    created_at       = ticket.created_at,
                    assisted_at      = ticket.assisted_at,                                      # <--- copy this for 8/9
                    assisted_by      = ticket.assisted_by.username if ticket.assisted_by else "N/A",  # <--- fallback
                    completed_at     = ticket.completed_at,
                    completed_by     = completed_by_user.username,                               # <--- copy real username for 11
                )
                print(f"[ARCHIVE FULL] Created for {ticket.control_no} | assisted_at={ticket.assisted_at} | completed_by={completed_by_user.username}")
            else:
                print(f"[ARCHIVE] Skipped - already exists for {ticket.control_no}")

        except Exception as e:
            print(f"[ARCHIVE ERROR] {type(e).__name__}: {str(e)}")
            messages.error(request, f"Could not archive ticket: {str(e)}")
        
        messages.success(request, f"Ticket {ticket.control_no} marked as completed!")
    
    
    referer = request.META.get('HTTP_REFERER', '')
    if 'super' in referer or request.user.is_superuser:
        return redirect(f"{reverse('super_admin_dashboard')}?tab={current_tab}")
    return redirect(f"{reverse('staff_dashboard')}?tab={current_tab}")


@login_required
def archive_reports(request):
    # Group by year and month for accordion
    grouped = ArchivedTicket.objects.annotate(
        year=TruncYear('completed_at'),
        month=TruncMonth('completed_at')
    ).values('year', 'month').annotate(
        count=Count('id')
    ).order_by('-year', '-month')

    # All archived tickets
    archived_tickets = ArchivedTicket.objects.all().order_by('-completed_at')

    print("Archive page loaded - count:", archived_tickets.count())
    if archived_tickets.exists():
        print("First archived:", archived_tickets.first().control_no, archived_tickets.first().completed_at)
    
    else:
        print("No archived tickets found in database.")

    # IMPORTANT: Pass assisting_tickets so right panel works on archive page
    assisting_tickets = Ticket.objects.filter(status='assisting').order_by('-assisted_at')

    now = timezone.now()
    archived_with_color = []
    for ticket in archived_tickets:
        if ticket.completed_at:
            delta = now - ticket.completed_at
            minutes = delta.total_seconds() // 60
            if minutes >= 10:
                color_class = 'text-danger fw-bold'
            elif minutes >= 5:
                color_class = 'text-warning fw-bold'
            else:
                color_class = 'text-success'
        else:
            color_class = 'text-muted'
        archived_with_color.append((ticket, color_class))

    context = {
        'grouped_data': grouped,
        'archived_tickets': archived_tickets,
        'assisting_tickets': assisting_tickets,  # ← this makes right panel show current assisting tickets
    }

    return render(request, 'archive_reports.html', context)


@login_required
def reopen_ticket(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        
        # Only allow re-open if it's currently accepted (missing/overdue)
        if ticket.status != 'accepted':
            messages.error(request, f"Cannot re-open ticket {ticket.control_no} — status is '{ticket.status}'.")
            return redirect('staff_dashboard')
        
        # Reset only the assisting part — keep it accepted
        ticket.assisted_by = None
        ticket.assisted_at = None
        # status stays 'accepted' — no change needed
        ticket.save()
        
        # Log it
        AuditLog.objects.create(
            user=request.user,
            action='reopened accepted ticket',
            details=f'Ticket {ticket.control_no} re-opened from missing/overdue by {request.user.username} (remains accepted)',
            ticket=ticket,
            ip_address=get_client_ip(request)
        )
        
        messages.success(request, f"Ticket {ticket.control_no} re-opened and moved back to Accepted.")
    
    # Redirect to Accepted tab
    return redirect(f"{reverse('staff_dashboard')}?tab=accepted")


@login_required
@require_http_methods(["POST"])  
def update_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    current_tab = request.POST.get('tab', 'new')
    
    if ticket.status not in ['accepted', 'assisting']:
        messages.error(request, f"Cannot update ticket {ticket.control_no} — current status is '{ticket.status}'.")
        return redirect('staff_dashboard')
       
    updated = False
    
    # Update fields only if they were sent and different
    if 'request_complaint' in request.POST:
        new_value = request.POST.get('request_complaint', '').strip()
        if new_value != ticket.request_complaint:
            ticket.request_complaint = new_value
            updated = True
    
    if 'equipment' in request.POST:
        new_value = request.POST.get('equipment', '').strip()
        if new_value != (ticket.equipment or ''):
            ticket.equipment = new_value
            updated = True
    
    if 'brand' in request.POST:
        new_value = request.POST.get('brand', '').strip()
        if new_value != (ticket.brand or ''):
            ticket.brand = new_value
            updated = True
    
    if 'model' in request.POST:
        new_value = request.POST.get('model', '').strip()
        if new_value != (ticket.model or ''):
            ticket.model = new_value
            updated = True
    
    if 'department_division' in request.POST:
        new_value = request.POST.get('department_division', '').strip()
        if new_value != ticket.department_division:
            ticket.department_division = new_value
            updated = True
    
    if 'section_unit' in request.POST:
        new_value = request.POST.get('section_unit', '').strip()
        if new_value != (ticket.section_unit or ''):
            ticket.section_unit = new_value
            updated = True
    
    if 'is_urgent' in request.POST:
        new_urgent = request.POST.get('is_urgent') == 'on'  # checkbox sends 'on'
        if new_urgent != ticket.is_urgent:
            ticket.is_urgent = new_urgent
            updated = True
    
    if 'requested_by' in request.POST:
        new_value = request.POST.get('requested_by', '').strip()
        if new_value != ticket.requested_by:
            ticket.requested_by = new_value
            updated = True
    
    if updated:
        ticket.is_manually_modified = True  
        ticket.save()
        
        changed_fields = []
        if 'request_complaint' in request.POST: changed_fields.append('complaint')
        if 'equipment' in request.POST:         changed_fields.append('equipment')
        if 'brand' in request.POST:             changed_fields.append('brand')
        if 'model' in request.POST:             changed_fields.append('model')
        if 'department_division' in request.POST: changed_fields.append('department')
        if 'section_unit' in request.POST:      changed_fields.append('section')
        if 'is_urgent' in request.POST:         changed_fields.append('urgent')
        if 'requested_by' in request.POST:      changed_fields.append('requester')
        
        AuditLog.objects.create(
            user=request.user,
            action='updated ticket fields',
            details=f'Ticket {ticket.control_no} updated by {request.user.username} from IP {get_client_ip(request)} (fields: {", ".join(changed_fields)})',  # ← CHANGE THIS line
            ticket=ticket,  
            ip_address=get_client_ip(request)  
        )
        
        messages.success(request, f"Ticket {ticket.control_no} updated successfully!")
    else:
        messages.info(request, "No changes were made to the ticket.")
    
    return redirect(f"{reverse('staff_dashboard')}?tab={current_tab}")

@login_required
def generate_report(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="it_tickets_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Control No', 'Requested By', 'Division', 'Status',
        'Created', 'Elapsed Time', 'Urgent', 'Description (short)'
    ])

    for ticket in Ticket.objects.all().order_by('-created_at'):
        writer.writerow([
            ticket.control_no,
            ticket.requested_by,
            f"{ticket.department_division or 'N/A'} - {ticket.section_unit or 'N/A'}",  # fixed line
            ticket.status,
            ticket.created_at.strftime('%Y-%m-%d %H:%M'),
            ticket.elapsed_time() if hasattr(ticket, 'elapsed_time') else '',
            'Yes' if ticket.is_urgent else 'No',
            ticket.request_complaint[:100] + '...' if len(ticket.request_complaint) > 100 else ticket.request_complaint,
        ])

    return response

@login_required
def admin_logout(request):
    user = request.user
    logout(request)
    
    AuditLog.objects.create(
        user=user,
        action='logout',
        details=f'{user.username} logged out',
        ip_address=get_client_ip(request)
    )
    
    messages.success(request, "You have been successfully logged out.")
    if user.is_superuser:
        return redirect('superadmin_login')  
    else:
        return redirect('staff_login')      

@login_required
def live_queue(request):
    all_tickets = Ticket.objects.all()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        def ticket_data(t):
            return {
                'control_no': t.control_no,
                'division_section': t.division_section,
                'requested_by': t.requested_by,
                'is_urgent': t.is_urgent,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
                'elapsed': timesince(t.created_at) if t.created_at else '',
                'status': t.status,
                'assisted_by': t.assisted_by.username if t.assisted_by else None,
                'assisted_at': t.assisted_at.strftime('%Y-%m-%d %H:%M') if t.assisted_at else None,
                'completed_at': t.completed_at.strftime('%Y-%m-%d %H:%M') if t.completed_at else None,
            }

        data = {
            'new_requests': [ticket_data(t) for t in all_tickets.filter(status='pending').order_by('created_at')],
            'accepted': [ticket_data(t) for t in all_tickets.filter(status='accepted').order_by('created_at')],
            'assisting': [ticket_data(t) for t in all_tickets.filter(status='assisting').order_by('assisted_at')],
            'completed': [ticket_data(t) for t in all_tickets.filter(status='completed').order_by('-completed_at')[:10]],
        }
        return JsonResponse(data)

    # HTML mode
    new_requests = all_tickets.filter(status='pending').annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-urgency_priority', 'created_at')

    accepted = all_tickets.filter(status='accepted').annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-urgency_priority', 'created_at')

    assisting = all_tickets.filter(status='assisting').annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-urgency_priority', 'assisted_at')

    completed = all_tickets.filter(status='completed').order_by('-completed_at')[:10]

    context = {
        'new_requests': new_requests,
        'accepted': accepted,
        'assisting': assisting,
        'completed': completed,
    }

    return render(request, 'live_queue.html', context)





#SUPER ADMIN SIDE 

# Superadmin side
def is_superadmin(user):
    return user.is_superuser


@login_required
@user_passes_test(is_superadmin, login_url='staff_login')
def superadmin_dashboard(request):
    all_tickets = Ticket.objects.all()

    def get_ordered_qs(qs):
        return qs.annotate(
            urgency_priority=Case(
                When(is_urgent=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        ).order_by('-urgency_priority', 'created_at')

    seven_days_ago = timezone.now() - timedelta(days=7)
    missing_threshold = timezone.now() - timedelta(hours=24)

    recent_activity = AuditLog.objects.select_related('user').order_by('-timestamp')[:15]

    # New Request tab: pending + accepted (unassigned)
    new_tickets = all_tickets.filter(
        status__in=['pending', 'accepted']
    ).annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-urgency_priority', '-created_at')

    # Missing / Overdue tab
    missing_tickets = all_tickets.filter(
        status__in=['pending', 'accepted'],
        created_at__lt=missing_threshold
    ).annotate(
        urgency_priority=Case(
            When(is_urgent=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('created_at')

    context = {
        'new_count': new_tickets.count(),
        'accepted_count': all_tickets.filter(status='assisting').count(),
        'completed_count': all_tickets.filter(
            status='completed',
            completed_at__gte=seven_days_ago
        ).count(),
        'missing_tasks_count': missing_tickets.count(),

        'pending_tickets': new_tickets,
        'accepted_tickets': get_ordered_qs(all_tickets.filter(status='assisting')),
        'completed_tickets': get_ordered_qs(
            all_tickets.filter(
                status='completed',
                completed_at__gte=seven_days_ago
            )
        ),
        'missing_tickets': missing_tickets,

        'assisting_tickets': get_ordered_qs(all_tickets.filter(status='assisting')),

        'staff_users': User.objects.filter(
            is_staff=True,
            is_superuser=False
        ).order_by('username'),

        'recent_activity': recent_activity,

        'tab': request.GET.get('tab', 'new'),
    }

    return render(request, 'super_admin_dashboard.html', context)


@login_required
@user_passes_test(is_superadmin, login_url='staff_login')
def superadmin_manage_users(request):
    staff_users = User.objects.filter(
        is_staff=True,
        is_superuser=False
    ).order_by('last_name', 'first_name', 'username')

    assisting_tickets = Ticket.objects.filter(status='assisting').order_by('-assisted_at')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_admin':
            username       = request.POST.get('username', '').strip()
            password1      = request.POST.get('password1', '')
            password2      = request.POST.get('password2', '')
            first_name     = request.POST.get('first_name', '').strip()
            last_name      = request.POST.get('last_name', '').strip()
            email          = request.POST.get('email', '').strip()
            contact_number = request.POST.get('contact_number', '').strip()
            designation    = request.POST.get('designation', '').strip()

            errors = []

            if not username:
                errors.append("Username is required.")
            if User.objects.filter(username=username).exists():
                errors.append("Username already taken.")
            if password1 != password2:
                errors.append("Passwords do not match.")
            if len(password1) < 8:
                errors.append("Password must be at least 8 characters.")
            if not password1:
                errors.append("Password is required.")
            if not first_name or not last_name:
                errors.append("First name and last name are required.")

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                if errors:
                    return JsonResponse({'success': False, 'errors': errors})

            if errors:
                messages.error(request, " • ".join(errors))
            else:
                try:
                    # This is the ONLY correct way — it hashes the password automatically
                    user = User.objects.create_user(
                        username=username,
                        password=password1,  # ← critical line: hashes password1
                        email=email or None,
                        first_name=first_name,
                        last_name=last_name,
                    )
                    user.is_staff = True
                    user.is_active = True
                    user.is_superuser = False
                    user.save()  

                    profile = StaffProfile.objects.create(user=user)
                    profile.contact_number = contact_number or None
                    profile.designation    = designation or None
                    profile.email          = email or None
                    profile.full_name      = f"{first_name} {last_name}".strip() or username
                    profile.username       = username
                    profile.save()

                    AuditLog.objects.create(
                        user=request.user,
                        action='created admin',
                        details=f'Admin {username} created by {request.user.username} from IP {get_client_ip(request)}',  # ← ADD THIS whole block
                        ip_address=get_client_ip(request)
                    )

                    full_name = f"{first_name} {last_name}".strip() or username

                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({'success': True})
                    else:
                        messages.success(request, f"New admin created: {full_name} (@{username})")
                        return redirect('manage_users')

                except Exception as e:
                    error_msg = f"Failed to create user: {str(e)}"
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'errors': [error_msg]})
                    else:
                        messages.error(request, error_msg)
                        return redirect('manage_users')

        elif action == 'delete_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id, is_staff=True, is_superuser=False)

            if user == request.user:
                messages.error(request, "You cannot delete yourself.")
            else:
                username = user.username
                user.delete()
                AuditLog.objects.create(
                    user=request.user,
                    action='deleted admin',
                    details=f'Admin {username} deleted by {request.user.username} from IP {get_client_ip(request)}',  # ← ADD THIS whole block
                    ip_address=get_client_ip(request)
                )
                messages.success(request, f"Admin '{username}' has been deleted.")

            return redirect('manage_users')

        elif action == 'update_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id, is_staff=True, is_superuser=False)

            username       = request.POST.get('username', '').strip()
            first_name     = request.POST.get('first_name', '').strip()
            last_name      = request.POST.get('last_name', '').strip()
            email          = request.POST.get('email', '').strip()
            contact_number = request.POST.get('contact_number', '').strip()
            designation    = request.POST.get('designation', '').strip()
            password       = request.POST.get('password', '').strip()
            is_active      = 'is_active' in request.POST

            errors = []

            if username and username != user.username:
                if User.objects.filter(username=username).exclude(id=user.id).exists():
                    errors.append("Username already taken.")

            user.first_name = first_name
            user.last_name  = last_name
            user.email      = email
            user.is_active  = is_active

            if password:
                if len(password) < 8:
                    errors.append("New password must be at least 8 characters.")
                else:
                    user.set_password(password)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' and errors:
                return JsonResponse({'success': False, 'errors': errors})

            if errors:
                messages.error(request, " • ".join(errors))
            else:
                user.save()

                profile, _ = StaffProfile.objects.get_or_create(user=user)
                profile.contact_number = contact_number or None
                profile.designation    = designation or None
                profile.email          = email or None
                profile.full_name      = f"{first_name} {last_name}".strip() or user.username
                profile.username       = username
                profile.save()

                AuditLog.objects.create(
                    user=request.user,
                    action='updated admin',
                    details=f'Admin {user.username} updated by {request.user.username} from IP {get_client_ip(request)}',  # ← ADD THIS whole block
                    ip_address=get_client_ip(request)
                )

                full_name = f"{user.first_name} {user.last_name}".strip() or user.username

                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': True})
                else:
                    messages.success(request, f"Updated {full_name} (@{user.username}) successfully.")
                    return redirect('manage_users')

    # GET request - show the staff table
    add_form = UserCreationForm()
    context = {
        'staff_users': staff_users,
        'add_form': add_form,
        'assisting_tickets': assisting_tickets,
    }

    return render(request, 'manage_users.html', context)


# Add new admin user (separate page/view)
@login_required
@user_passes_test(is_superadmin, login_url='staff_login')
def add_admin_user(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = True           # can access staff dashboard
            user.is_superuser = False      # not a superadmin
            user.save()
            messages.success(request, f"New admin user '{user.username}' created successfully!")
            return redirect('manage_users')
        else:
            messages.error(request, "Form invalid — check username/password rules.")
    else:
        form = UserCreationForm()
    
    return render(request, 'add_admin.html', {'form': form})


# Superadmin-only login page
def superadmin_login(request):

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        print("Form bound:", form.is_bound)
        print("Form valid:", form.is_valid())
        print("Form errors:", form.errors.as_json() if form.errors else "No errors")

        if form.is_valid():
            user = form.get_user()
            print("User found:", user.username if user else "None")
            print("is_superuser:", user.is_superuser if user else "N/A")

            if user.is_superuser:
                login(request, user)
                print("Login SUCCESS → redirecting to dashboard")

                AuditLog.objects.create(
                    user=user,
                    action='login',
                    details=f'Superadmin {user.username} logged in from IP {get_client_ip(request)}',
                    ip_address=get_client_ip(request)
                )

                return redirect('super_admin_dashboard')
                
            else:
                print("User is NOT superuser")
                messages.error(request, "This login is only for Super Admins.")
        else:
            print("Form INVALID")
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    # Add Bootstrap classes to form fields
    form.fields['username'].widget.attrs.update({'class': 'form-control'})
    form.fields['password'].widget.attrs.update({'class': 'form-control'})

    return render(request, 'superadmin_login.html', {'form': form})

@login_required
def audit_logs(request):
    # Base queryset - newest first
    logs = AuditLog.objects.select_related('user', 'ticket').order_by('-timestamp')

    logs = logs.exclude(action__icontains='login').exclude(action__icontains='logout')

    # Filter type (All / Audit Trail / Deletion Logs)
    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'audit_trail':
        logs = logs.exclude(action__icontains='deleted')
    elif filter_type == 'deletion_logs':
        logs = logs.filter(action__icontains='deleted')

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        logs = logs.filter(
            Q(details__icontains=search) |
            Q(user__username__icontains=search) |
            Q(action__icontains=search)
        )

    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    # Admin filter
    selected_admin = request.GET.get('admin')
    if selected_admin and selected_admin != 'all':
        logs = logs.filter(user__username=selected_admin)

    # Action type filter (optional - can expand)
    selected_action = request.GET.get('action_type')
    if selected_action and selected_action != 'all':
        logs = logs.filter(action__icontains=selected_action)

    # Prepare context
    context = {
        'logs': logs,
        'filter_type': filter_type,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'selected_admin': selected_admin,
        'selected_action': selected_action,
        'total_logs': AuditLog.objects.count(),
        'admins': User.objects.filter(is_staff=True).order_by('username').values_list('username', flat=True).distinct(),
        'action_types': [
            'Accept', 'Assign', 'Assisting', 'Completed', 'Deleted',
            'Created Ticket', 'Updated Ticket', 'Created Admin', 'Updated Admin', 'Deleted Admin'
        ],
    }

    return render(request, 'audit_logs.html', context)


@login_required
@user_passes_test(is_superadmin, login_url='staff_login')
def superadmin_archive(request):
    archived_tickets = ArchivedTicket.objects.all().order_by('-completed_at')

    # 1. Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        archived_tickets = archived_tickets.filter(completed_at__date__gte=date_from)
    if date_to:
        archived_tickets = archived_tickets.filter(completed_at__date__lte=date_to)

    # 2. Completed by user filter
    completed_by_id = request.GET.get('completed_by')
    if completed_by_id and completed_by_id != 'all':
        from .models import AuditLog
        completed_ticket_ids = AuditLog.objects.filter(
            action='completed ticket',
            user_id=completed_by_id
        ).values_list('ticket__id', flat=True).distinct()
        archived_tickets = archived_tickets.filter(control_no__in=Ticket.objects.filter(id__in=completed_ticket_ids).values_list('control_no', flat=True))

    # 3. Attach completer name + original ticket data for modal
    from .models import AuditLog, Ticket
    for ticket in archived_tickets:
        # Who completed it
        completer_log = AuditLog.objects.filter(
            ticket__control_no=ticket.control_no,
            action='completed ticket'
        ).order_by('-timestamp').first()
        ticket.completer_name = completer_log.user.username if completer_log and completer_log.user else "Unknown"

        # Original ticket details (only existing fields)
        original_ticket = Ticket.objects.filter(control_no=ticket.control_no).first()
        if original_ticket:
            ticket.original_description = original_ticket.request_complaint
            ticket.original_equipment   = original_ticket.equipment or "N/A"
            ticket.original_brand       = original_ticket.brand or "N/A"
            ticket.original_model       = original_ticket.model or "N/A"
            ticket.original_department  = original_ticket.department_division or "N/A"  
            ticket.original_section     = original_ticket.section_unit or "N/A"        
            ticket.is_modified          = original_ticket.is_manually_modified
        else:
            ticket.original_description = ticket.description
            ticket.original_equipment   = "N/A"
            ticket.original_brand       = "N/A"
            ticket.original_model       = "N/A"
            ticket.original_department  = ticket.division or "N/A"                     
            ticket.original_section     = "N/A"
            ticket.is_modified          = False

    # 4. All staff for dropdown
    all_staff = User.objects.filter(is_staff=True).order_by('username')

    # 5. Context
    context = {
        'archived_tickets': archived_tickets,
        'all_staff': all_staff,
        'selected_date_from': date_from,
        'selected_date_to': date_to,
        'selected_completed_by': completed_by_id,
    }

    return render(request, 'super_admin_archive.html', context)



def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
@user_passes_test(is_superadmin, login_url='staff_login')
def all_tickets(request):
    all_tickets = Ticket.objects.all().order_by('-created_at')

    # Tab filter (like staff dashboard)
    tab = request.GET.get('tab', 'pending')

    if tab == 'pending':
        tickets = all_tickets.filter(status='pending').order_by('-created_at')
    elif tab == 'accepted':
        tickets = all_tickets.filter(status='accepted').order_by('-accepted_at')
    elif tab == 'assisting':
        tickets = all_tickets.filter(status='assisting').order_by('-assisted_at')
    elif tab == 'completed':
        tickets = all_tickets.filter(status='completed').order_by('-completed_at')
    else:
        tickets = all_tickets

    context = {
        'all_tickets': all_tickets,
        'tickets': tickets,
        'tab': tab,
        'total_tickets': all_tickets.count(),
        'pending_count': all_tickets.filter(status='pending').count(),
        'accepted_count': all_tickets.filter(status='accepted').count(),
        'assisting_count': all_tickets.filter(status='assisting').count(),
        'completed_count': all_tickets.filter(status='completed').count(),
    }

    return render(request, 'all_tickets.html', context)







@login_required
def reports(request):
    # ── Get filters ──
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str   = request.GET.get('date_to', '').strip()
    division      = request.GET.get('division', '').strip()
    status_filter = request.GET.get('status', '').strip()
    export_type   = request.GET.get('export', '')

    queryset = Ticket.objects.all()

    # ── Apply filters ──
    if date_from_str:
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                date_from = datetime.strptime(date_from_str, fmt).date()
                queryset = queryset.filter(created_at__date__gte=date_from)
                break
            except ValueError:
                continue

    if date_to_str:
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                date_to = datetime.strptime(date_to_str, fmt).date()
                queryset = queryset.filter(created_at__date__lte=date_to)
                break
            except ValueError:
                continue

    if division:
        queryset = queryset.filter(department_division=division)

    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # ── Calculate KPIs (always, for PDF/HTML) ──
    total_requests   = queryset.count()
    completed_count  = queryset.filter(status='completed').count()
    accepted_count   = queryset.filter(status='accepted').count()
    pending_count    = queryset.filter(status='pending').count()
    urgent_count     = queryset.filter(is_urgent=True).count()

    completion_rate = round((completed_count / total_requests * 100), 1) if total_requests > 0 else 0.0
    urgent_percent  = round((urgent_count / total_requests * 100), 1) if total_requests > 0 else 0.0

    avg_resolution = "N/A"
    avg_qs = queryset.filter(status='completed', completed_at__isnull=False, created_at__isnull=False)
    if avg_qs.exists():
        time_diff = ExpressionWrapper(F('completed_at') - F('created_at'), output_field=DurationField())
        avg_dur = avg_qs.aggregate(avg=Avg(time_diff))['avg']
        if avg_dur and avg_dur.total_seconds() > 0:
            hours = avg_dur.total_seconds() / 3600
            avg_resolution = f"{hours:.1f}h"

    # Chart data (HTML only)
    daily_data = queryset.annotate(day=TruncDay('created_at')) \
                         .values('day') \
                         .annotate(count=Count('id')) \
                         .order_by('day')
    chart_labels = [d['day'].strftime('%Y-%m-%d') for d in daily_data] if daily_data else []
    chart_data   = [d['count'] for d in daily_data] if daily_data else []

    status_breakdown = {
        'new': pending_count,
        'accepted': accepted_count,
        'completed': completed_count,
        'urgent': urgent_count,
        'total': total_requests
    }

    divisions_qs = Ticket.objects.values_list('department_division', flat=True)\
                                 .distinct().exclude(department_division__isnull=True).order_by('department_division')

    filtered_tickets = queryset.order_by('-created_at')[:500]

    # ── Export: Excel ──
    if export_type == 'excel':
        response = HttpResponse(content_type='text/csv')
        filename = f"ticket_report_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Control No', 'Requested By', 'Division', 'Status', 'Urgent',
            'Created At', 'Completed At', 'Resolution Hours', 'Description'
        ])

        for t in filtered_tickets:
            res_hours = ''
            if t.completed_at and t.created_at:
                delta = t.completed_at - t.created_at
                res_hours = round(delta.total_seconds() / 3600, 1)

            writer.writerow([
                t.control_no,
                t.requested_by or 'N/A',
                t.department_division or 'N/A',
                t.status.title(),
                'Yes' if t.is_urgent else 'No',
                t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
                t.completed_at.strftime('%Y-%m-%d %H:%M') if t.completed_at else '',
                res_hours,
                (t.request_complaint[:200] + '...') if t.request_complaint and len(t.request_complaint) > 200 else (t.request_complaint or '')
            ])
        return response

        # ── Export: PDF (Clean, No Cropping, DOH Style + Fixes) ──
    if export_type == 'pdf':
 
        # ── Colors ──
        DOH_BLUE     = colors.HexColor('#1a3a6b')
        DOH_LIGHT    = colors.HexColor('#1565c0')
        DOH_GOLD     = colors.HexColor('#f9c900')
        DOH_LIGHT_BG = colors.HexColor('#f0f4f8')
        DOH_ROW_ALT  = colors.HexColor('#e8f0fb')
        WHITE        = colors.white
        GRAY_TEXT    = colors.HexColor('#5a7a9a')
        DARK         = colors.HexColor('#1a1a2e')
        RED_URGENT   = colors.HexColor('#c0392b')
        GREEN_OK     = colors.HexColor('#1a7a4a')
 
        # ── Logo paths — update these to your actual static file paths ──
        import os
        APP_DIR  = os.path.dirname(os.path.abspath(__file__))
        LOGO_BP  = os.path.join(APP_DIR, 'static', 'images', 'BAGONG_PILIPINAS_LOGO.png')
        LOGO_DOH = os.path.join(APP_DIR, 'static', 'images', 'DOH_LOGO.png')
        LOGO_CHD = os.path.join(APP_DIR, 'static', 'images', 'CHD4A.png')
 
        # ── Report metadata ──
        admin_name   = request.user.get_full_name() or request.user.username
        ref_no       = f"DOH-CHD-CAL-ITH-{timezone.now().strftime('%Y%m%d-%H%M')}"
        period_str   = f"{date_from_str or 'All'} – {date_to_str or 'Present'}"
        report_title = "IT Helpdesk Report"
        
 
        # ── Page header/footer callback ──
        def draw_page(canvas, doc):
            canvas.saveState()
            W, H = A4
 
            # Header bar
            canvas.setFillColor(DOH_BLUE)
            canvas.rect(0, H - 70, W, 70, fill=1, stroke=0)
            canvas.setFillColor(DOH_GOLD)
            canvas.rect(0, H - 73, W, 3, fill=1, stroke=0)
 
            # Logos
            for path, x in [(LOGO_BP, 10), (LOGO_DOH, 58)]:
                if os.path.exists(path):
                    canvas.drawImage(path, x, H - 63, width=44, height=44,
                                     preserveAspectRatio=True, mask='auto')
 
            # Divider
            canvas.setStrokeColor(colors.HexColor('#ffffff60'))
            canvas.setLineWidth(1)
            canvas.line(110, H - 60, 110, H - 15)
 
            # Header text
            canvas.setFillColor(colors.HexColor('#ffffffcc'))
            canvas.setFont('Helvetica', 7.5)
            canvas.drawString(118, H - 28, 'Republic of the Philippines  ·  Department of Health')
            canvas.setStrokeColor(colors.HexColor('#ffffff40'))
            canvas.setLineWidth(0.5)
            canvas.line(118, H - 33, 420, H - 33)
            canvas.setFillColor(WHITE)
            canvas.setFont('Helvetica-Bold', 11)
            canvas.drawString(118, H - 48, 'CENTER FOR HEALTH DEVELOPMENT - CALABARZON ')
            canvas.setFillColor(colors.HexColor('#ffffffaa'))
            canvas.setFont('Helvetica', 7)
            canvas.drawString(118, H - 60, 'Information and Communications Technology Division')
 
            # CHD logo right
            if os.path.exists(LOGO_CHD):
                canvas.drawImage(LOGO_CHD, W - 60, H - 63, width=46, height=46,
                                 preserveAspectRatio=True, mask='auto')
 
            # Sub-header bar
            canvas.setFillColor(DOH_LIGHT_BG)
            canvas.rect(0, H - 100, W, 27, fill=1, stroke=0)
            canvas.setStrokeColor(colors.HexColor('#dde6f0'))
            canvas.setLineWidth(0.5)
            canvas.line(0, H - 100, W, H - 100)
            canvas.setFillColor(DOH_BLUE)
            canvas.setFont('Helvetica-Bold', 8.5)
            canvas.drawString(20, H - 90, report_title.upper())
            canvas.setFillColor(GRAY_TEXT)
            canvas.setFont('Helvetica', 7.5)
            canvas.drawRightString(W - 20, H - 86, f'Ref: {ref_no}')
            canvas.drawRightString(W - 20, H - 95, f'Period: {period_str}')
 
            # Footer
            canvas.setFillColor(DOH_BLUE)
            canvas.rect(0, 0, W, 32, fill=1, stroke=0)
            canvas.setFillColor(DOH_GOLD)
            canvas.rect(0, 32, W, 2, fill=1, stroke=0)
            canvas.setFillColor(WHITE)
            canvas.setFont('Helvetica', 7)
            canvas.drawString(20, 18, 'DOH CHD CALABARZON  ·  ICT Helpdesk System  ·  For official use only.')
            canvas.drawRightString(W - 20, 18, f'Generated by: {admin_name}   |   Page {doc.page}')
            canvas.restoreState()
 
        # ── Paragraph styles ──
        def S(name, **kw):
            from reportlab.lib.styles import ParagraphStyle
            return ParagraphStyle(name, **kw)
 
        section_title = S('SecTitle', fontSize=9, fontName='Helvetica-Bold', textColor=DOH_BLUE,
                           spaceAfter=6, spaceBefore=14, leading=12,
                           backColor=DOH_LIGHT_BG, leftIndent=-4, rightIndent=-4)
        normal_s = S('NormalS', fontSize=8, fontName='Helvetica', textColor=DARK, leading=11)
        small_s  = S('SmallS',  fontSize=7, fontName='Helvetica', textColor=GRAY_TEXT, leading=10)
        bold_s   = S('BoldS',   fontSize=8, fontName='Helvetica-Bold', textColor=DARK, leading=11)
 
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=20*mm, leftMargin=20*mm,
            topMargin=115, bottomMargin=45,
        )
 
        elements = []
 
        # ── Report Info ──
        elements.append(Paragraph("REPORT INFORMATION", section_title))
        info_data = [
            ['Report Reference No.', ref_no,              'Generated By',   admin_name],
            ['Date Generated', timezone.now().strftime('%B %d, %Y %I:%M %p'), 'Period Covered', period_str],
            ['Division Filter', division or 'All Divisions', 'Status Filter', status_filter or 'All Statuses'],
        ]
        info_table = Table(info_data, colWidths=[100, 155, 95, 150])
        info_table.setStyle(TableStyle([
            ('FONTNAME',    (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE',    (0,0), (-1,-1), 7.5),
            ('FONTNAME',    (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME',    (2,0), (2,-1), 'Helvetica-Bold'),
            ('TEXTCOLOR',   (0,0), (0,-1), GRAY_TEXT),
            ('TEXTCOLOR',   (2,0), (2,-1), GRAY_TEXT),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [WHITE, DOH_LIGHT_BG]),
            ('GRID',        (0,0), (-1,-1), 0.3, colors.HexColor('#dde6f0')),
            ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',  (0,0), (-1,-1), 5),
            ('BOTTOMPADDING',(0,0),(-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(info_table)
 
        # ── KPI Summary ──
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("SUMMARY OF REQUESTS", section_title))
        kpi_rows = [
            ('Total Requests Received',    str(total_requests),  'Within selected period'),
            ('Completed / Resolved',       str(completed_count), f'{completion_rate}% completion rate'),
            ('Accepted / In Progress',     str(accepted_count),  'Currently being handled'),
            ('Pending / New Requests',     str(pending_count),   'Awaiting review or assignment'),
            ('Urgent / Priority Requests', str(urgent_count),    f'{urgent_percent}% of total requests'),
            ('Average Resolution Time',    str(avg_resolution),  'Average hours from filing to completion'),
        ]
        kpi_data = [[
            Paragraph('<b>Performance Indicator</b>', bold_s),
            Paragraph('<b>Value</b>', bold_s),
            Paragraph('<b>Remarks</b>', bold_s),
        ]]
        for row in kpi_rows:
            kpi_data.append([
                Paragraph(row[0], normal_s),
                Paragraph(f'<b>{row[1]}</b>', bold_s),
                Paragraph(row[2], small_s),
            ])
        kpi_table = Table(kpi_data, colWidths=[210, 80, 210])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND',   (0,0), (-1,0), DOH_BLUE),
            ('TEXTCOLOR',    (0,0), (-1,0), WHITE),
            ('FONTNAME',     (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',     (0,0), (-1,0), 8.5),
            ('ALIGN',        (0,0), (-1,0), 'CENTER'),
            ('LINEBELOW',    (0,0), (-1,0), 2, DOH_GOLD),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [DOH_ROW_ALT, WHITE]),
            ('GRID',         (0,0), (-1,-1), 0.4, colors.HexColor('#c0cfe0')),
            ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',   (0,0), (-1,-1), 6),
            ('BOTTOMPADDING',(0,0), (-1,-1), 6),
            ('LEFTPADDING',  (0,0), (-1,-1), 8),
            ('ALIGN',        (1,1), (1,-1), 'CENTER'),
        ]))
        elements.append(kpi_table)
 
        # ── Detailed Tickets ──
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("DETAILED TICKET RECORDS", section_title))
 
        tkt_header = [
            Paragraph('<b>Control No.</b>',       bold_s),
            Paragraph('<b>Requested By</b>',      bold_s),
            Paragraph('<b>Division / Section</b>', bold_s),
            Paragraph('<b>Status</b>',             bold_s),
            Paragraph('<b>Priority</b>',           bold_s),
            Paragraph('<b>Date Filed</b>',         bold_s),
            Paragraph('<b>Nature of Request</b>',  bold_s),
        ]
        status_colors_map = {
            'completed': GREEN_OK,
            'assisting': DOH_LIGHT,
            'pending':   colors.HexColor('#856404'),
            'accepted':  colors.HexColor('#0c5460'),
        }
        tkt_data = [tkt_header]
        for i, t in enumerate(filtered_tickets):
            sc = status_colors_map.get(t.status, DARK)
            st_style = S(f'St{i}', fontSize=7.5, fontName='Helvetica-Bold', textColor=sc, leading=10)
            ctrl_style = S(f'Ctrl{i}', fontSize=7, fontName='Helvetica-Bold', textColor=DOH_BLUE, leading=10)
            div_text = t.department_division or 'N/A'
            if t.section_unit:
                div_text += f' — {t.section_unit}'
            created_str = t.created_at.strftime('%m/%d/%Y %I:%M %p') if t.created_at else 'N/A'
            tkt_data.append([
                Paragraph(t.control_no or 'N/A', ctrl_style),
                Paragraph(t.requested_by or 'N/A', normal_s),
                Paragraph(div_text, small_s),
                Paragraph(t.status.title(), st_style),
                Paragraph('<font color="red"><b>URGENT</b></font>' if t.is_urgent else 'Normal', normal_s),
                Paragraph(created_str, small_s),
                Paragraph((t.request_complaint or '')[:120], normal_s),
            ])
 
        if len(tkt_data) > 1:
            tkt_table = Table(tkt_data, colWidths=[72, 72, 100, 52, 48, 72, 84],
                              repeatRows=1, splitByRow=1)
            tkt_table.setStyle(TableStyle([
                ('BACKGROUND',   (0,0), (-1,0), DOH_BLUE),
                ('TEXTCOLOR',    (0,0), (-1,0), WHITE),
                ('FONTNAME',     (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',     (0,0), (-1,0), 8),
                ('ALIGN',        (0,0), (-1,0), 'CENTER'),
                ('LINEBELOW',    (0,0), (-1,0), 2, DOH_GOLD),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [DOH_ROW_ALT, WHITE]),
                ('GRID',         (0,0), (-1,-1), 0.3, colors.HexColor('#c0cfe0')),
                ('VALIGN',       (0,0), (-1,-1), 'TOP'),
                ('TOPPADDING',   (0,0), (-1,-1), 5),
                ('BOTTOMPADDING',(0,0), (-1,-1), 5),
                ('LEFTPADDING',  (0,0), (-1,-1), 5),
                ('RIGHTPADDING', (0,0), (-1,-1), 5),
                ('ALIGN',        (0,1), (0,-1), 'CENTER'),
                ('ALIGN',        (3,1), (3,-1), 'CENTER'),
                ('ALIGN',        (4,1), (4,-1), 'CENTER'),
            ]))
            elements.append(tkt_table)
        else:
            elements.append(Paragraph("No tickets match the selected filters.", normal_s))
 
        # ── Certification ──
        elements.append(Spacer(1, 20))
        cert_table = Table([[
            Paragraph(
                'This report has been generated by the ICT Division of DOH-CHD CALABARZON '
                'and reflects the official records of the IT Helpdesk System as of the date indicated above. '
                'This document is for <b>official use only</b>. Unauthorized disclosure or reproduction is strictly prohibited.',
                S('Cert', fontSize=7.5, fontName='Helvetica', textColor=GRAY_TEXT, leading=11,
                  alignment=TA_JUSTIFY)
            )
        ]], colWidths=[500])
        cert_table.setStyle(TableStyle([
            ('BOX',          (0,0), (-1,-1), 0.5, colors.HexColor('#dde6f0')),
            ('BACKGROUND',   (0,0), (-1,-1), DOH_LIGHT_BG),
            ('LEFTPADDING',  (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING',   (0,0), (-1,-1), 10),
            ('BOTTOMPADDING',(0,0), (-1,-1), 10),
        ]))
        elements.append(cert_table)
 
        doc.build(elements, onFirstPage=draw_page, onLaterPages=draw_page)
        pdf_bytes = buffer.getvalue()
        buffer.close()
 
        response = HttpResponse(content_type='application/pdf')
        filename = f"DOH_IT_Helpdesk_Report_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(pdf_bytes)
        return response

    # ── Normal HTML view ──
    context = {
        'total_requests': total_requests,
        'completed_count': completed_count,
        'accepted_count': accepted_count,
        'pending_count': pending_count,
        'urgent_count': urgent_count,
        'completion_rate': completion_rate,
        'urgent_percent': urgent_percent,
        'avg_resolution': avg_resolution,
        'tickets_over_time': {'labels': chart_labels, 'data': chart_data},
        'status_breakdown': status_breakdown,
        'divisions': divisions_qs,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'selected_division': division,
        'selected_status': status_filter,
        'filtered_tickets': filtered_tickets,
        'show_table': queryset.exists(),
    }

    return render(request, 'reports.html', context)







    




@login_required
def archived_ticket_print(request, pk):
    ticket = get_object_or_404(ArchivedTicket, pk=pk)
    action_options = ActionTakenOption.objects.all()

    assisted_by_full_name = ticket.assisted_by or "ICT Personnel"
    if ticket.assisted_by:
        try:
            user = User.objects.get(username=ticket.assisted_by)
            full = user.get_full_name()
            if full:
                assisted_by_full_name = full
            else:
                # fallback to StaffProfile
                from .models import StaffProfile
                profile = StaffProfile.objects.filter(user=user).first()
                if profile and profile.full_name:
                    assisted_by_full_name = profile.full_name
        except User.DoesNotExist:
            pass

    return render(request, 'archived_ticket_print.html', {
        'ticket': ticket,
        'action_options': action_options,
        'assisted_by_full_name': assisted_by_full_name,
    })


@login_required
@require_POST
def save_action_taken(request):
    try:
        data = json.loads(request.body)
        pk = data.get('pk')
        text = data.get('action_taken')

        ticket = get_object_or_404(ArchivedTicket, pk=pk)
        ticket.action_taken = text
        ticket.save()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    



@login_required
@require_POST
def add_action_taken_option(request):
    try:
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            ActionTakenOption.objects.get_or_create(name=name)
            return JsonResponse({'success': True})
    except:
        pass
    return JsonResponse({'success': False})





