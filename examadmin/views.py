from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import Exam
@csrf_exempt
def delete_multiple_exams(request):
if request.method == 'POST':
try:
data = json.loads(request.body)
exam_ids = data.get('exam_ids', [])
if not isinstance(exam_ids, list) or not exam_ids:
return JsonResponse({"error": "Invalid or empty exam_ids list provided."}, status=400)
# Validate and delete exams
deleted_count, _ = Exam.objects.filter(id__in=exam_ids).delete()
return JsonResponse({"status": "success", "deleted_count": deleted_count}, status=200)
except json.JSONDecodeError:
return JsonResponse({"error": "Invalid JSON payload."}, status=400)
return JsonResponse({"error": "Only POST requests are allowed."}, status=405)