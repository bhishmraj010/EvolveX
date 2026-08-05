from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class BlogPost(models.Model):
    """A blog post. Manage these from the Django admin — no code changes needed to add a post."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
    )
    cover_image = models.ImageField(upload_to="blog_covers/", blank=True, null=True)
    excerpt = models.CharField(
        max_length=300,
        blank=True,
        help_text="Short summary shown on the blog list page.",
    )
    content = models.TextField(help_text="Full post content. Line breaks are preserved.")
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:200] or "post"
            slug = base_slug
            counter = 1
            while BlogPost.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def reading_time_minutes(self):
        words = len(self.content.split())
        return max(1, round(words / 200))


class ContactMessage(models.Model):
    """One submission from the Contact Us form."""

    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.submitted_at:%Y-%m-%d %H:%M}"
