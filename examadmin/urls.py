from django.urls import path
from . import views
urlpatterns = [
# Other existing routes
path('results/delete/', views.delete_exam_results, name='delete_exam_results'),
]