from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from home import views as home_views   # jaha bhi tera home_view hai wahan se import kar

urlpatterns = [
    path('admin/',     admin.site.urls),
    path('',           home_views.home_view, name='home'),   # ← naya home page yaha
    path('home/',      include('home.urls')),                # ← journal save/etc + about/contact/blog
    path('robots.txt', home_views.robots_txt_view, name='robots_txt'),
    path('sitemap.xml', home_views.sitemap_xml_view, name='sitemap_xml'),
    path('users/',     include('users.urls')),
    path('dashboard/', include('tasks.urls')),
    path('tracker/',   include('tracker.urls')),
    path('reports/',   include('reports.urls')),
    path('diet/',      include('diet.urls')),
    path('analyzer/',  include('analyzer.urls')),
    path('roadmap/',   include('roadmap.urls')),
    path('subscriptions/', include('subscriptions.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)