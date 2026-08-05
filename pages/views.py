from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ContactForm
from .models import BlogPost


def about_us(request):
    return render(request, "pages/about.html")


def contact_us(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_msg = form.save()

            # Optional: also email the team, if CONTACT_NOTIFY_EMAIL is set in settings.py
            # and email backend (EMAIL_HOST etc.) is configured. Safe no-op otherwise.
            admin_email = getattr(settings, "CONTACT_NOTIFY_EMAIL", None)
            if admin_email:
                try:
                    send_mail(
                        subject=f"[EvolveX Contact] {contact_msg.subject or 'New message'}",
                        message=f"From: {contact_msg.name} <{contact_msg.email}>\n\n{contact_msg.message}",
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[admin_email],
                        fail_silently=True,
                    )
                except Exception:
                    pass  # never break the user-facing flow because of email issues

            messages.success(request, "Thanks! Your message has been received — we'll get back to you soon.")
            return redirect("contact_us")
    else:
        form = ContactForm()

    return render(request, "pages/contact.html", {"form": form})


def blog_list(request):
    posts = BlogPost.objects.filter(is_published=True)
    return render(request, "pages/blog_list.html", {"posts": posts})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    related = BlogPost.objects.filter(is_published=True).exclude(pk=post.pk)[:3]
    return render(request, "pages/blog_detail.html", {"post": post, "related": related})
