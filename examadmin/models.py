from django.db import models
class Exam(models.Model):
name = models.CharField(max_length=255)
def __str__(self):
return self.name
class ExamResult(models.Model):
exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="results")
student_name = models.CharField(max_length=255)
score = models.IntegerField()
def __str__(self):
return f"{self.student_name} - {self.exam.name}"