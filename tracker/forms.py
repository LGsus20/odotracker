from decimal import Decimal

from django import forms

from .models import MaintenanceEntry, Part


class EntryForm(forms.ModelForm):
    """Create/update a maintenance entry.

    Field-level constraints (required, type, ``PositiveIntegerField`` for km)
    come from the model for free via ``ModelForm``. The odometer "cannot go
    backwards" rule lives on the model's ``clean()`` so it is enforced
    everywhere; this form surfaces those errors per-field.
    """

    class Meta:
        model = MaintenanceEntry
        fields = ['name', 'kilometers', 'cost', 'date', 'reason']
        widgets = {
            'kilometers': forms.NumberInput(attrs={'inputmode': 'numeric'}),
            'cost': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'reason': forms.Textarea(attrs={'placeholder': 'Optional details…'}),
        }

    def clean_cost(self):
        cost = self.cleaned_data.get('cost')
        if cost is None:
            return cost
        if cost < Decimal('0'):
            raise forms.ValidationError('Cost must be a positive number.')
        return cost


class PartForm(forms.ModelForm):
    """Create/update a tracked part.

    The "at least one interval" rule lives on the model's ``clean()`` and
    surfaces here as a non-field error. Fields are rendered by hand in the
    template (same as the entry form), so no widgets are declared here.
    """

    class Meta:
        model = Part
        fields = ['name', 'interval_km', 'interval_months']


class ServiceForm(forms.Form):
    """Log a performed service for a part.

    Not a ModelForm: saving creates two objects (the linked MaintenanceEntry
    plus the ServiceRecord) in the view. ``date`` arrives via the hidden ISO
    input filled by the template's date widget (same pattern as EntryForm);
    ``note`` feeds the entry's reason and is capped at 255 chars.
    """
    part = forms.ModelChoiceField(queryset=Part.objects.all(), empty_label=None)
    kilometers = forms.IntegerField(min_value=0)
    cost = forms.DecimalField(min_value=Decimal('0'), required=False)
    date = forms.DateTimeField()
    note = forms.CharField(max_length=255, required=False)