from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
import uuid
import datetime

class User(AbstractUser):
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=50, default='admin')
    
    def __str__(self):
        return self.username

class Branch(models.Model):
    name = models.CharField(max_length=255, unique=True)
    logo = models.ImageField(upload_to='branch_logos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Branches"
        ordering = ['id']
    
    def __str__(self):
        return self.name

class Subject(models.Model):
    name = models.CharField(max_length=255)
    is_foreign_language = models.BooleanField(default=False, help_text="Bu fənn xarici dil fənnidir")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['id']
        unique_together = ('name', 'is_foreign_language')
    
    def __str__(self):
        return self.name

class Class(models.Model):
    name = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Classes"
        ordering = ['id']
    
    def __str__(self):
        return self.name

class Section(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return self.name

class Group(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['id']



class Exam(models.Model):
    EXAM_TYPES = [
        ('9-cu sinif buraxılış', '9-cu sinif buraxılış'),
        ('11-ci sinif buraxılış', '11-ci sinif buraxılış'),
        ('Blok imtahanı', 'Blok imtahanı'),
        ('Magistratura', 'Magistratura'),
        ('Bilik yarışı', 'Bilik yarışı'),
        ('Təkmilləşdirmə', 'Təkmilləşdirmə'),
        ('Müəllimlərin İşə Qəbulu', 'Müəllimlərin İşə Qəbulu'),
        ('Sertifikasiya', 'Sertifikasiya'),
        ('Dövlət Qulluğu', 'Dövlət Qulluğu'),
        ('Azərbaycan dili (dövlət dili kimi)', 'Azərbaycan dili (dövlət dili kimi)'),
        ('10-cu sinif buraxılış', '10-cu sinif buraxılış'),
    ]
    
    name = models.CharField(max_length=500)
    date = models.DateField()
    type = models.CharField(max_length=50, choices=EXAM_TYPES)
    branches = models.ManyToManyField(Branch, related_name='exams')
    classes = models.ManyToManyField(Class, related_name='exams', blank=True)
    sections = models.ManyToManyField(Section, related_name='exams')
    groups = models.ManyToManyField(Group, related_name='exams')
    participant_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def save(self, *args, **kwargs):
        sections = Section.objects.all()
        super().save(*args, **kwargs)
        self.sections.add(*sections)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    @property
    def branch_count(self):
        return self.branches.count()

class SectionDetail(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='section_details')
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    variant_count = models.PositiveIntegerField(default=1)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    group_name = models.CharField(max_length=255,null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['exam', 'section', 'group']
    
    def __str__(self):
        return f"{self.exam.name} - {self.section.name} - {self.group.name}"
    
    @property
    def subject_count(self):
        return self.exam_subjects.count()

class ExamSubject(models.Model):
    section_detail = models.ForeignKey(SectionDetail, on_delete=models.CASCADE, related_name='exam_subjects')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    question_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['section_detail', 'subject']
    
    def __str__(self):
        return f"{self.section_detail} - {self.subject.name}"

class StudentResult(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]
    
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='student_results')
    student_name = models.CharField(max_length=255)
    work_number = models.CharField(max_length=50)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    contact_number = models.CharField(max_length=20,null=True, blank=True)
    school_number = models.CharField(max_length=50, null=True, blank=True)  # School number field
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    variant = models.CharField(max_length=10,null=True, blank=True)
    section = models.ForeignKey(Section, on_delete=models.CASCADE,null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    total_score = models.DecimalField(max_digits=6, decimal_places=2,null=True, blank=True)
    class_level = models.ForeignKey(Class, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=False)
    additional_datas = models.JSONField(default=dict, blank=True)  # For storing any additional data
    
    answer_card_pdf = models.FileField(
        upload_to='answer_cards/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        null=True,
        blank=True
    )
    pdfToken = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    original_answers = models.JSONField(default=dict, blank=True)  # Store original answers as JSON
    
    class Meta:
        unique_together = ['exam', 'work_number']
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.student_name} - {self.work_number}"

class NotUploadedStudentResult(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='not_uploaded_results')
    student_name = models.CharField(max_length=255)
    work_number = models.CharField(max_length=50)


class SubjectResult(models.Model):
    student_result = models.ForeignKey(StudentResult, on_delete=models.CASCADE, related_name='subject_results')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    total_questions = models.PositiveIntegerField()
    correct_answers = models.PositiveIntegerField()
    wrong_answers = models.PositiveIntegerField()
    empty_answers = models.PositiveIntegerField()
    score = models.DecimalField(max_digits=6, decimal_places=2)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    subject_data = models.JSONField(default=list, blank=True)  # For storing additional subject data
    
    
    class Meta:
        unique_together = ['student_result', 'subject']
    
    def __str__(self):
        return f"{self.student_result.student_name} - {self.subject.name}"

class CorrectAnswerCombination(models.Model):
    CATEGORY_CHOICES = [
        ("BB","BB"),
        ("BA","BA"),
    ]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='correct_answers')
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    combination_uid = models.CharField(max_length=36)
    variant = models.CharField(max_length=10)
    class_level = models.ForeignKey(Class, on_delete=models.CASCADE, null=True, blank=True)
    category = models.CharField(max_length=50, null=True, blank=True,choices=CATEGORY_CHOICES)  # e.g., 'Mathematics', 'Science'
    group_name = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['exam', 'section', 'variant', 'class_level', 'group_name']
    
    def __str__(self):
        return f"{self.exam.name} - {self.section.name} - {self.variant}"

class CorrectAnswer(models.Model):
    
    combination = models.ForeignKey(CorrectAnswerCombination, on_delete=models.CASCADE, related_name='answers')
    question_number = models.PositiveIntegerField()
    correct_answer = models.CharField(max_length=10,null=True, blank=True)
    score = models.DecimalField(max_digits=20, decimal_places=10, default=1.0)
    penalty_score = models.DecimalField(max_digits=20, decimal_places=10, default=0.0)
    is_multiple_choice = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    question_type = models.CharField(max_length=50, null=True, blank=True,choices=[
        ('close', 'Qapalı'),
        ('open_coded', 'Kodlaşdırıla bilən açıq tipli'),
        ('open', 'İzahlı açıq tipli'),
        ('true_false', 'Doğru/Yanlış'),
        ('essay', 'Esse'),
        ('matching', 'Uyğunlaşdırma'),

    ])  
    
    def __str__(self):
        return f"Q{self.question_number}: {self.correct_answer}"
    class Meta:
        ordering = ['id']

class ImportLog(models.Model):
    IMPORT_TYPES = [
        ('results', 'Results Import'),
        ('correct_answers', 'Correct Answers Import'),
        ('answer_cards', 'Answer Cards Import'),
    ]
    
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='import_logs')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='import_logs', null=True, blank=True)
    import_type = models.CharField(max_length=20, choices=IMPORT_TYPES, default='results')
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()  # in bytes
    records_imported = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    imported_by = models.ForeignKey(User, on_delete=models.CASCADE,default=None, null=True, blank=True, related_name='import_logs')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.import_type} - {self.file_name}"