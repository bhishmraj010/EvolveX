from django.urls import path

from . import views

urlpatterns = [
    path("about/", views.about_us, name="about_us"),
    path("contact/", views.contact_us, name="contact_us"),
    path("blog/", views.blog_list, name="blog_list"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
]
