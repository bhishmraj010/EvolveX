from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser


COUNTRY_CODES = [
    ('+91', '🇮🇳 +91 India'),
    ('+1', '🇺🇸 +1 USA/Canada'),
    ('+44', '🇬🇧 +44 UK'),
    ('+61', '🇦🇺 +61 Australia'),
    ('+971', '🇦🇪 +971 UAE'),
    ('+966', '🇸🇦 +966 Saudi Arabia'),
    ('+974', '🇶🇦 +974 Qatar'),
    ('+65', '🇸🇬 +65 Singapore'),
    ('+49', '🇩🇪 +49 Germany'),
    ('+33', '🇫🇷 +33 France'),
    ('+81', '🇯🇵 +81 Japan'),
    ('+86', '🇨🇳 +86 China'),
    ('+880', '🇧🇩 +880 Bangladesh'),
    ('+92', '🇵🇰 +92 Pakistan'),
    ('+94', '🇱🇰 +94 Sri Lanka'),
]


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(
        attrs={'placeholder': 'your@email.com', 'class': 'form-input'}
    ))
    name = forms.CharField(max_length=100, required=False, widget=forms.TextInput(
        attrs={'placeholder': 'Display name (optional)', 'class': 'form-input'}
    ))

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'placeholder': 'Choose a username', 'class': 'form-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'placeholder': 'Password (min 8 chars)', 'class': 'form-input'
        })
        self.fields['password2'].widget.attrs.update({
            'placeholder': 'Confirm password', 'class': 'form-input'
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.name  = self.cleaned_data.get('name', '')
        if commit:
            user.save()
        return user


class CompleteProfileForm(forms.Form):
    """Shown once, right after a brand-new Google sign-in, so every account
    (whether it started via Google or the regular form) ends up with a
    username, a usable password, and a unique phone number."""
    username = forms.CharField(
        max_length=25,
        widget=forms.TextInput(attrs={'placeholder': 'Choose a username', 'class': 'form-input'}),
    )
    country_code = forms.ChoiceField(
        choices=COUNTRY_CODES, initial='+91',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    phone_number = forms.CharField(
        max_length=15, required=True,
        widget=forms.TextInput(attrs={'placeholder': '98765 43210', 'class': 'form-input'}),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Password (min 8 chars)', 'class': 'form-input'}),
    )
    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm password', 'class': 'form-input'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('That username is already taken.')
        return username

    def clean_phone_number(self):
        # Just the national number here — digits only, no country code yet
        # (that gets prefixed in clean() once both fields are available).
        digits = self.cleaned_data['phone_number'].strip().replace(' ', '').replace('-', '')
        if not digits.isdigit():
            raise forms.ValidationError('Enter digits only, without the country code.')
        if not (6 <= len(digits) <= 12):
            raise forms.ValidationError('Enter a valid phone number.')
        return digits

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        validate_password(password1)
        return password1

    def clean(self):
        cleaned = super().clean()

        # Combine country code + national number into one E.164-style value.
        country_code = cleaned.get('country_code')
        national_number = cleaned.get('phone_number')
        if country_code and national_number:
            full_phone = f'{country_code}{national_number}'
            if CustomUser.objects.filter(phone_number=full_phone).exists():
                self.add_error('phone_number', 'An account with this phone number already exists.')
            # Overwrite with the combined value — downstream code (views.py)
            # reads cleaned_data['phone_number'] as-is and saves it straight
            # to CustomUser.phone_number.
            cleaned['phone_number'] = full_phone

        # Password match check.
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')

        return cleaned


class OTPForm(forms.Form):
    """The 6-digit email verification code entered on the verify_otp page."""
    otp = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': '6-digit code',
            'class': 'form-input',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': True,
        }),
    )

    def clean_otp(self):
        otp = self.cleaned_data['otp'].strip()
        if not otp.isdigit():
            raise forms.ValidationError('Enter the 6-digit numeric code.')
        return otp


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(
        attrs={'placeholder': 'Username', 'class': 'form-input', 'autofocus': True}
    ))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'placeholder': 'Password', 'class': 'form-input'}
    ))


class ProfileForm(forms.ModelForm):
    class Meta:
        model  = CustomUser
        fields = ('name', 'email', 'phone_number', 'avatar', 'bio')
        widgets = {
            'name':  forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+91XXXXXXXXXX'}),
            'bio':   forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'placeholder': 'your@email.com', 'class': 'form-input', 'autofocus': True}
    ))

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if not CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('No account found with this email.')
        return email


class ResetPasswordForm(forms.Form):
    """Shown together on one page: enter the OTP that was emailed, plus
    the new password — mirrors the OTPForm style used for signup."""
    otp = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': '6-digit code',
            'class': 'form-input',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': True,
        }),
    )
    new_password1 = forms.CharField(
        label='New password',
        widget=forms.PasswordInput(attrs={'placeholder': 'New password (min 8 chars)', 'class': 'form-input'}),
    )
    new_password2 = forms.CharField(
        label='Confirm new password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm new password', 'class': 'form-input'}),
    )

    def clean_otp(self):
        otp = self.cleaned_data['otp'].strip()
        if not otp.isdigit():
            raise forms.ValidationError('Enter the 6-digit numeric code.')
        return otp

    def clean_new_password1(self):
        password1 = self.cleaned_data.get('new_password1')
        validate_password(password1)
        return password1

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('new_password1'), cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned