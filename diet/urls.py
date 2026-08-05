from django.urls import path
from . import views

urlpatterns = [
    path('',                       views.diet_home,          name='diet'),
    path('onboarding/',            views.onboarding,         name='diet_onboarding'),
    path('onboarding/details/',    views.onboarding_details, name='diet_onboarding_details'),
    path('plan/',                  views.diet_plan_result,   name='diet_plan_result'),
    path('add/',                   views.add_meal,           name='diet_add_meal'),
    path('add-photo/',             views.confirm_meal_photo, name='diet_confirm_photo'),
    path('delete/<int:meal_id>/',  views.delete_meal,        name='diet_delete_meal'),
    path('cheat/<int:meal_id>/',   views.toggle_cheat,       name='diet_toggle_cheat'),
    path('profile/edit/',          views.edit_profile,       name='diet_edit_profile'),
    path('api/search/',            views.search_food,        name='diet_search_food'),
    path('api/ai-lookup/',         views.ai_lookup_food,     name='diet_ai_lookup'),
    path('api/analyze-photo/',     views.analyze_meal_photo, name='diet_analyze_photo'),
]