from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.dashboard,    name='dashboard'),
    path('todo/',                   views.todo_list,    name='todo_list'),
    path('add/',                    views.add_task,     name='add_task'),
    path('complete/<int:task_id>/', views.complete_task, name='complete_task'),
    path('skip/<int:task_id>/',     views.skip_task,    name='skip_task'),
    path('delete/<int:task_id>/',   views.delete_task,  name='delete_task'),
    path('undo/<int:task_id>/',     views.undo_task,    name='undo_task'),

    # Boss battle
    path('boss/',                                        views.boss_battle,        name='boss_battle'),
    path('boss/challenge/<int:challenge_id>/complete/',   views.complete_challenge, name='complete_challenge'),
    path('boss/<int:boss_id>/defeat/',                    views.defeat_boss,        name='defeat_boss'),
]