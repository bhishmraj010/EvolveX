from django.db import models
from django.conf import settings
from django.utils import timezone

# ── Points ──────────────────────────────────────────────────────────────────
DIET_WIN_POINTS    = 10   # calories within goal range
DIET_CHEAT_PENALTY = 5    # cheat meal per day


PHYSIQUE_CHOICES = [
    ('lean',     'Lean & Athletic'),
    ('cut',      'Weight Loss (Fat Cut)'),
    ('maintain', 'Maintain Physique'),
    ('bulk',     'Bulk (Mass Gain)'),
    ('custom',   'Custom Plan'),
]

ACTIVITY_CHOICES = [
    ('sedentary',   'Sedentary (No exercise)'),
    ('light',       'Light (1-2x/week)'),
    ('moderate',    'Moderate (3-4x/week)'),
    ('active',      'Active (5-6x/week)'),
    ('very_active', 'Very Active (2x/day)'),
]

GENDER_CHOICES = [
    ('male',   'Male'),
    ('female', 'Female'),
    ('other',  'Other'),
]

# Physique visual data for onboarding cards
PHYSIQUE_CARDS = {
    'lean': {
        'emoji': '⚡',
        'title': 'Lean & Athletic',
        'desc': 'Build muscle while staying lean. High protein, moderate carbs.',
        'color': '#4cff91',
    },
    'cut': {
        'emoji': '🔥',
        'title': 'Fat Cut',
        'desc': 'Lose fat, preserve muscle. Caloric deficit with high protein.',
        'color': '#ff4c6b',
    },
    'maintain': {
        'emoji': '⚖️',
        'title': 'Maintain',
        'desc': 'Stay at current weight. Balanced macros at maintenance calories.',
        'color': '#7c6fff',
    },
    'bulk': {
        'emoji': '💪',
        'title': 'Bulk Up',
        'desc': 'Maximum muscle gain. Caloric surplus, heavy compound lifts.',
        'color': '#f5c842',
    },
    'custom': {
        'emoji': '✏️',
        'title': 'Custom Plan',
        'desc': 'Set your own calorie & macro targets manually.',
        'color': '#9896a8',
    },
}


class DietProfile(models.Model):
    user             = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='diet_profile')
    gender           = models.CharField(max_length=10, choices=GENDER_CHOICES, default='male')
    age              = models.PositiveIntegerField(default=25)
    weight_kg        = models.FloatField()
    height_cm        = models.FloatField()
    activity_level   = models.CharField(max_length=20, choices=ACTIVITY_CHOICES, default='moderate')
    physique_goal    = models.CharField(max_length=20, choices=PHYSIQUE_CHOICES, default='maintain')

    daily_calories   = models.IntegerField(default=2000)
    protein_g        = models.IntegerField(default=150)
    carbs_g          = models.IntegerField(default=250)
    fat_g            = models.IntegerField(default=65)

    ai_plan          = models.TextField(blank=True)
    calorie_tolerance = models.IntegerField(default=10)

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} | {self.physique_goal} | {self.daily_calories} kcal"

    def calorie_lower(self):
        return int(self.daily_calories * (1 - self.calorie_tolerance / 100))

    def calorie_upper(self):
        return int(self.daily_calories * (1 + self.calorie_tolerance / 100))


class FoodItem(models.Model):
    UNIT_CHOICES = [
        ('g',    'Grams'),
        ('ml',   'Milliliters'),
        ('pcs',  'Pieces'),
        ('cup',  'Cup'),
        ('tbsp', 'Tablespoon'),
        ('tsp',  'Teaspoon'),
    ]

    name              = models.CharField(max_length=200)
    calories_per_100  = models.FloatField()
    protein_per_100   = models.FloatField(default=0)
    carbs_per_100     = models.FloatField(default=0)
    fat_per_100       = models.FloatField(default=0)
    base_unit         = models.CharField(max_length=10, choices=UNIT_CHOICES, default='g')
    user              = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                          on_delete=models.CASCADE, related_name='custom_foods')
    ai_estimated      = models.BooleanField(default=False)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.calories_per_100} kcal/100{self.base_unit})"

    def get_macros(self, quantity):
        factor = quantity / 100
        return {
            'calories': round(self.calories_per_100 * factor, 1),
            'protein':  round(self.protein_per_100  * factor, 1),
            'carbs':    round(self.carbs_per_100    * factor, 1),
            'fat':      round(self.fat_per_100      * factor, 1),
        }


class MealLog(models.Model):
    MEAL_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch',     'Lunch'),
        ('dinner',    'Dinner'),
        ('snack',     'Snack'),
    ]

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='meal_logs')
    date        = models.DateField(default=timezone.now)
    meal_type   = models.CharField(max_length=15, choices=MEAL_CHOICES, default='lunch')
    food_item   = models.ForeignKey(FoodItem, null=True, blank=True, on_delete=models.SET_NULL)
    food_name   = models.CharField(max_length=200, blank=True)
    quantity    = models.FloatField(default=100)
    unit        = models.CharField(max_length=10, default='g')
    calories    = models.FloatField(default=0)
    protein_g   = models.FloatField(default=0)
    carbs_g     = models.FloatField(default=0)
    fat_g       = models.FloatField(default=0)
    is_cheat    = models.BooleanField(default=False)
    notes       = models.TextField(blank=True)
    image       = models.ImageField(upload_to='meal_photos/%Y/%m/%d/', blank=True, null=True)
    ai_analyzed = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['meal_type', 'created_at']

    def display_name(self):
        return self.food_item.name if self.food_item else self.food_name


class DietLog(models.Model):
    STATUS_CHOICES = [
        ('win',     'Goal Met'),
        ('survive', 'Close'),
        ('lose',    'Missed'),
        ('ongoing', 'Ongoing'),
    ]

    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='diet_logs')
    date            = models.DateField(default=timezone.now)
    total_calories  = models.FloatField(default=0)
    total_protein   = models.FloatField(default=0)
    total_carbs     = models.FloatField(default=0)
    total_fat       = models.FloatField(default=0)
    has_cheat_meal  = models.BooleanField(default=False)
    day_status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ongoing')
    points_earned   = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.user} | {self.date} | {self.total_calories} kcal | {self.day_status}"