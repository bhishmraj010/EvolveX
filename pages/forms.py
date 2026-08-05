from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "message"]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Your name", "class": "pg-input", "autocomplete": "name",
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "you@example.com", "class": "pg-input", "autocomplete": "email",
            }),
            "subject": forms.TextInput(attrs={
                "placeholder": "Subject (optional)", "class": "pg-input",
            }),
            "message": forms.Textarea(attrs={
                "placeholder": "How can we help?", "class": "pg-textarea", "rows": 6,
            }),
        }
