# ticketing_queue/forms.py
from django import forms
from .models import Ticket, ActionTaken


class TicketForm(forms.ModelForm):
    # Hidden/manual date/time fields (kept as-is)
    date_mm = forms.CharField(max_length=2, required=True)
    date_dd = forms.CharField(max_length=2, required=True)
    date_yyyy = forms.CharField(max_length=4, required=True)
    time = forms.CharField(max_length=5, required=True)
    ampm = forms.ChoiceField(choices=[('AM', 'AM'), ('PM', 'PM')], required=True)

    # Main fields – matching your current model exactly
    department_division = forms.CharField(
        max_length=150,
        required=True,
        label="Department / Division"
    )
    section_unit = forms.CharField(
        max_length=150,
        required=False,
        label="Section / Unit"
    )

    brand = forms.CharField(
        max_length=100,
        required=False,
        label="Brand (if applicable)"
    )
    model = forms.CharField(
        max_length=100,
        required=False, 
        label="Model (if known)"
    )

    class Meta:
        model = Ticket
        fields = [
            'request_complaint',
            'equipment',
            'brand',
            'model',
            'department_division',
            'section_unit',
            'is_urgent',
            'requested_by',
            'date_mm', 'date_dd', 'date_yyyy', 'time', 'ampm',
        ]
        widgets = {
            'request_complaint': forms.Textarea(attrs={'rows': 4}),
            'is_urgent': forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: add placeholders or help text
        self.fields['brand'].widget.attrs.update({'placeholder': '-- Select or type brand --'})
        self.fields['model'].widget.attrs.update({'placeholder': '-- Select or type model (optional) --'})

    def clean(self):
        cleaned_data = super().clean()

        # Require department_division
        if not cleaned_data.get('department_division'):
            self.add_error('department_division', "Please select a Department / Division.")

        # Model is optional – no error if empty
        # Brand is optional – no error if empty

        return cleaned_data


class ActionTakenForm(forms.ModelForm):
    class Meta:
        model = ActionTaken
        fields = ['date', 'time', 'am_pm', 'action_taken', 'action_officer', 'job_confirmation']
        widgets = {
            'action_taken': forms.Textarea(attrs={'rows': 4}),
            'job_confirmation': forms.Textarea(attrs={'rows': 3}),
        }