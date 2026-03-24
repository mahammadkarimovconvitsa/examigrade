from django.test import TestCase, Client
from django.urls import reverse
from .models import Exam, ExamResult
class DeleteExamResultsTestCase(TestCase):
def setUp(self):
self.client = Client()
self.url = reverse('delete_exam_results')
# Create sample exam and results
self.exam = Exam.objects.create(name="Sample Exam")
ExamResult.objects.create(exam=self.exam, student_name="John Doe", score=85)
ExamResult.objects.create(exam=self.exam, student_name="Jane Doe", score=90)
def test_delete_exam_results_success(self):
response = self.client.post(self.url, data={"exam_id": self.exam.id}, content_type="application/json")
self.assertEqual(response.status_code, 200)
self.assertEqual(response.json()['status'], 'success')
self.assertEqual(response.json()['deleted_count'], 2)
self.assertFalse(ExamResult.objects.filter(exam=self.exam).exists())
def test_delete_exam_results_invalid_exam_id(self):
response = self.client.post(self.url, data={"exam_id": 999}, content_type="application/json")
self.assertEqual(response.status_code, 404)
self.assertEqual(response.json()['error'], "No results found for the specified exam.")
def test_delete_exam_results_missing_parameter(self):
response = self.client.post(self.url, data={}, content_type="application/json")
self.assertEqual(response.status_code, 400)
self.assertEqual(response.json()['error'], "Missing or invalid 'exam_id' parameter.")
def test_delete_exam_results_non_post_method(self):
response = self.client.get(self.url)
self.assertEqual(response.status_code, 405)
self.assertEqual(response.json()['error'], "Only POST requests are allowed.")