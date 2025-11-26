from django.urls import path
from .views import *

app_name = 'budgets'

urlpatterns = [
    path('fill/', BudgetView.as_view(), name='budget-view'),
    path('base-average/', BaseAverageView.as_view(), name='base-average-view'),
    path('living-average/',LivingAvgView.as_view(), name='living-average-view'),
    path('total-average/', TotalAvgView.as_view(), name='total-average-view'),
]