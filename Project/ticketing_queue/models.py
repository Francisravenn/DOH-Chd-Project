from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.conf import settings   # ← Important import
from django.contrib.auth.models import User


class StaffProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile' 
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    designation    = models.CharField(max_length=100, blank=True, null=True)
    email          = models.EmailField(blank=True, null=True)           
    full_name      = models.CharField(max_length=150, blank=True, null=True)  
    username       = models.CharField(max_length=150, blank=True, null=True)  
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile: {self.user.username}"

    class Meta:
        verbose_name = "Staff Profile"
        verbose_name_plural = "Staff Profiles"


class Ticket(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('assisting', 'Assisting'),
        ('completed', 'Completed'),
        ('follow_up_pending','Follow-Up Pending'), 
    )

    control_no = models.CharField(max_length=50, unique=True, blank=True)
    date_request = models.DateField()
    time_request = models.TimeField()
    am_pm = models.CharField(max_length=2, choices=(('AM', 'AM'), ('PM', 'PM')))
    request_complaint = models.TextField()
    equipment = models.CharField(max_length=100, blank=True, null=True)

    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)

    department_division = models.CharField(max_length=150, verbose_name="Department / Division")
    section_unit = models.CharField(max_length=150, blank=True, null=True, verbose_name="Section / Unit")

    is_urgent = models.BooleanField(default=False, verbose_name="Urgent Request")
    requested_by = models.CharField(max_length=150)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    division_section = models.CharField(max_length=255, blank=True, null=True)  # or whatever fits

    
    # FIXED: Use settings.AUTH_USER_MODEL
    assisted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assisted_tickets'
    )

    accepted_at = models.DateTimeField(null=True, blank=True, editable=False)
    assisted_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    is_being_assisted = models.BooleanField(default=False, editable=False)

    is_manually_modified = models.BooleanField(default=False)  
    def has_pending_follow_up(self):
        return self.follow_ups.filter(status='pending').exists()
    def elapsed_time(self):
        delta = timezone.now() - self.created_at
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        return f"{delta.days}d {hours}h {minutes}m"

    def generate_control_no(self):
        last_ticket = Ticket.objects.order_by('-id').first()
        next_num = (last_ticket.id + 1) if last_ticket else 1
        year = timezone.now().strftime('%Y')
        self.control_no = f"DOH4A-ICT-{year}-{next_num:04d}"

    def save(self, *args, **kwargs):
        self.clean()
        
        if not self.control_no:
            self.generate_control_no()

        old_status = None
        if self.pk:
            try:
                old = Ticket.objects.get(pk=self.pk)
                old_status = old.status
            except Ticket.DoesNotExist:
                pass

        now = timezone.now()

        if self.status == 'accepted' and old_status != 'accepted':
            self.accepted_at = now

        if self.status == 'assisting' and old_status != 'assisting':
            self.assisted_at = now

        if self.status == 'completed' and old_status != 'completed':
            self.completed_at = now

        self.is_being_assisted = (self.status == 'assisting')

        super().save(*args, **kwargs)


class ArchivedTicket(models.Model):
    control_no       = models.CharField(max_length=50, unique=True)
    requested_by     = models.CharField(max_length=200)
    division         = models.CharField(max_length=100)
    description      = models.TextField(blank=True)
    is_urgent        = models.BooleanField(default=False)
    created_at       = models.DateTimeField()
    completed_at     = models.DateTimeField()
    archived_at      = models.DateTimeField(auto_now_add=True)
    assisted_at = models.DateTimeField(null=True, blank=True)  
    assisted_by = models.CharField(max_length=150, blank=True)  
    completed_by = models.CharField(max_length=150)  
    action_taken = models.TextField(blank=True, null=True) 

    class Meta:
        verbose_name = "Archived Ticket"
        verbose_name_plural = "Archived Tickets"
        ordering = ['-completed_at']

    def __str__(self):
        return f"Archive - {self.control_no}"
    
    def save(self, *args, **kwargs):
        if not self.division:
            self.division = "N/A"  
        super().save(*args, **kwargs)


class ActionTaken(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE)
    date = models.DateField()
    time = models.TimeField()
    am_pm = models.CharField(max_length=2, choices=(('AM', 'AM'), ('PM', 'PM')))
    action_taken = models.TextField()
    action_officer = models.CharField(max_length=100)
    job_confirmation = models.TextField(blank=True)

    def __str__(self):
        return f"Action for {self.ticket.control_no}"


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    action = models.CharField(max_length=100)
    details = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    ticket = models.ForeignKey('Ticket', on_delete=models.SET_NULL, null=True, blank=True) 
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        unique_together = ['ticket', 'action']  

    def __str__(self):
        return f"{self.action} at {self.timestamp}"


class ITRequest(models.Model):
    control_number = models.CharField(max_length=30, unique=True, editable=False)
    requested_by = models.CharField(max_length=150)
    division = models.CharField(max_length=150)
    date_requested = models.DateField()
    time_requested = models.TimeField()
    am_pm = models.CharField(max_length=2, choices=[('AM', 'AM'), ('PM', 'PM')])
    description = models.TextField()
    equipment = models.CharField(max_length=200, blank=True)
    brand_model = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.control_number:
            year = timezone.now().year
            last = ITRequest.objects.filter(created_at__year=year).order_by('-created_at').first()
            seq = 1 if not last else int(last.control_number.split('-')[-1]) + 1
            self.control_number = f"QC-IT-{year}-{seq:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.control_number


class Command(BaseCommand):
    help = 'Copies old completed tickets into ArchivedTicket (only if missing)'

    def handle(self, *args, **options):
        completed = Ticket.objects.filter(status='completed').order_by('completed_at')

        if not completed.exists():
            self.stdout.write(self.style.WARNING("→ No completed tickets found in the database."))
            return

        created = 0
        skipped = 0
        failed = 0

        self.stdout.write(f"→ Found {completed.count()} completed tickets. Checking archive...")

        for ticket in completed:
            if ArchivedTicket.objects.filter(control_no=ticket.control_no).exists():
                skipped += 1
                continue

            try:
                ArchivedTicket.objects.create(
                    control_no       = ticket.control_no,
                    requested_by     = ticket.requested_by or "Unknown requester",
                    division         = ticket.department_division or ticket.section_unit or "N/A",
                    description      = ticket.request_complaint or "(no description was saved)",
                    is_urgent        = ticket.is_urgent,
                    created_at       = ticket.created_at,
                    completed_at     = ticket.completed_at,
                )
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  Created archive entry → {ticket.control_no}"))
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  Failed for {ticket.control_no}: {type(e).__name__} → {str(e)}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nFinished:\n"
            f"  • Created: {created}\n"
            f"  • Skipped (already exists): {skipped}\n"
            f"  • Failed: {failed}"
        ))

class ActionTakenOption(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class AdminOnlineStatus(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='online_status')
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.last_seen}"
    
class TicketFollowUp(models.Model):
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    ticket         = models.ForeignKey('Ticket', on_delete=models.CASCADE, related_name='follow_ups')
    message        = models.TextField()
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin          = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_follow_ups')
    admin_response = models.TextField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    reviewed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"FollowUp#{self.pk} on {self.ticket.control_no} [{self.status}]"
    
   