from django.urls import path
from . import views

urlpatterns = [
    path('journal/save/', views.journal_save_view, name='journal_save'),
    path('about/',        views.about_view,        name='about'),
    path('contact/',      views.contact_view,       name='contact'),
    path('blog/',         views.blog_list_view,     name='blog_list'),
]