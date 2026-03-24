from django.test import TestCase, Client
from django.urls import reverse
from .models import Exam
class DeleteMultipleExamsTestCase(TestCase):
def setUp(self):
self.client = Client()
self.url = reverse('delete_multiple_exams')
# Creating sample exams
Exam.objects.create(name="Exam 1")
Exam.objects.create(name="Exam 2")
Exam.objects.create(name="Exam 3")
def test_delete_multiple_exams_success(self):
exam_ids = list(Exam.objects.values_list('id', flat=True))
response = self.client.post(self.url, data={"exam_ids": exam_ids}, content_type="application/json")
self.assertEqual(response.status_code, 200)
self.assertEqual(response.json()['status'], 'success')
self.assertEqual(response.json()['deleted_count'], len(exam_ids))
self.assertFalse(Exam.objects.exists())
def test_delete_multiple_exams_invalid_payload(self):
response = self.client.post(self.url, data={"invalid_key": []}, content_type="application/json")
self.assertEqual(response.status_code, 400)
self.assertEqual(response.json()['error'], "Invalid or empty exam_ids list provided.")
def test_delete_multiple_exams_non_post_method(self):
response = self.client.get(self.url)
self.assertEqual(response.status_code, 405)
self.assertEqual(response.json()['error'], "Only POST requests are allowed.")