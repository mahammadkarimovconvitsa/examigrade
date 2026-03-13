from django.contrib import admin
from .models import User, Branch, Subject, Class, Section, Exam, StudentResult, SectionDetail , SubjectResult , ExamSubject , CorrectAnswer,CorrectAnswerCombination, Group, ImportLog, Specialization

# Register your models here.

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_foreign_language', 'is_active', 'created_at']
    list_filter = ['is_foreign_language', 'is_active']
    search_fields = ['name']
    
admin.site.register(User)
admin.site.register(Branch)
admin.site.register(Class)
admin.site.register(Section)
admin.site.register(Group)
admin.site.register(Exam)
admin.site.register(StudentResult)
admin.site.register(SectionDetail)
admin.site.register(SubjectResult)
admin.site.register(ExamSubject)
admin.site.register(CorrectAnswer)
admin.site.register(CorrectAnswerCombination)
admin.site.register(ImportLog)
admin.site.register(Specialization)