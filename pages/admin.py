from django.contrib import admin

from .models import BlogPost, ContactMessage


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_published", "published_at")
    list_filter = ("is_published",)
    search_fields = ("title", "content", "excerpt")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "submitted_at", "is_read")
    list_filter = ("is_read", "submitted_at")
    search_fields = ("name", "email", "message")
    readonly_fields = ("submitted_at",)
