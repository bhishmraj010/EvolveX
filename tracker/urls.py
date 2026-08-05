from django.urls import path
from . import views

urlpatterns = [
    path('willpower/',                         views.willpower,        name='willpower'),
    path('willpower/complete/<int:task_id>/',  views.complete_wp_task, name='complete_wp_task'),
    path('willpower/skip/<int:task_id>/',      views.skip_wp_task,     name='skip_wp_task'),
    path('willpower/delete/<int:task_id>/',    views.delete_wp_task,   name='delete_wp_task'),
    path('willpower/undo/<int:task_id>/',      views.undo_wp_task,     name='undo_wp_task'),
    path('diet/',                              views.diet,             name='diet'),
]