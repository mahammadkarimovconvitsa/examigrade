from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import ExamResult
@csrf_exempt
def delete_exam_results(request):
if request.method == 'POST':
try:
data = json.loads(request.body)
exam_id = data.get('exam_id')
if not exam_id:
return JsonResponse({"error": "Missing or invalid 'exam_id' parameter."}, status=400)
# Validate if exam exists
if not ExamResult.objects.filter(exam_id=exam_id).exists():
return JsonResponse({"error": "No results found for the specified exam."}, status=404)
# Delete results for the specified exam
deleted_count, _ = ExamResult.objects.filter(exam_id=exam_id).delete()
return JsonResponse({"status": "success", "deleted_count": deleted_count}, status=200)
except json.JSONDecodeError:
return JsonResponse({"error": "Invalid JSON payload."}, status=400)
return JsonResponse({"error": "Only POST requests are allowed."}, status=405)