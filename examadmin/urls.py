from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'branches', BranchViewSet)
router.register(r'subjects', SubjectViewSet)
router.register(r'classes', ClassViewSet)
router.register(r'sections', SectionViewSet)
router.register(r'exams', ExamViewSet)
router.register(r'groups', GroupViewSet)
router.register(r'specializations', SpecializationViewSet)
router.register(r'student-results', StudentResultViewSet, basename='studentresult')
router.register(r'result-card', ResultCardViewSet, basename='resultcard')
router.register(r'results', ResultsViewSet, basename='results')
router.register(r'exams-student', ExamsViewSet, basename='examtemplate')
router.register(r'stats', GetStatsViewSet, basename='stats')
router.register(r'export', ExportViewSet, basename='export')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/auth/login/', CustomAuthToken.as_view(), name='api_token_auth'),
    path('cavabKarti/',GetAnswerCardViewSet.as_view(), name='answer_card'),
]           