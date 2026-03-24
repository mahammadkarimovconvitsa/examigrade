from django.urls import path
from . import views
urlpatterns = [
# Other existing routes
path('exams/delete/', views.delete_multiple_exams, name='delete_multiple_exams'),
]