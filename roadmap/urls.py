from django.urls import path
from . import views

urlpatterns = [
    path("", views.roadmap_home, name="roadmap_home"),
    path("new/", views.onboarding, name="roadmap_onboarding"),
    path("new/<int:draft_id>/clarify/", views.submit_clarifying_answers, name="roadmap_clarify_submit"),
    path("<int:roadmap_id>/switch/", views.switch_roadmap, name="roadmap_switch"),
    path("<int:roadmap_id>/regenerate/", views.regenerate, name="roadmap_regenerate"),
    path("mission/<int:mission_id>/toggle/", views.toggle_mission_task, name="roadmap_toggle_task"),
    path("mission/<int:mission_id>/next/", views.generate_next_mission, name="roadmap_next_mission"),
    path("checkpoint/<int:checkpoint_id>/clear/", views.clear_checkpoint, name="roadmap_clear_checkpoint"),
    path("phase/<int:phase_id>/test/", views.take_test, name="roadmap_take_test"),
    path("test/<int:test_id>/submit/", views.submit_test, name="roadmap_submit_test"),
    path("phase/<int:phase_id>/remedial/", views.start_remedial, name="roadmap_start_remedial"),
    path('new/answer/<int:draft_id>/', views.submit_clarifying_answers, name='roadmap_submit_clarifying'),
]