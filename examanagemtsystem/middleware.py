# myapp/middleware.py
from django.http import JsonResponse

ALLOWED_ORIGINS = ["https://examigrade.oguznesriyyati.az","https://api.neticelerim.az","https://api.neticelerim.az","https://neticelerim.az", "http://localhost:3000", "http://localhost:3001"]

class BlockUnauthorizedMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get("HTTP_ORIGIN")
        referer = request.META.get("HTTP_REFERER")

        if origin and origin not in ALLOWED_ORIGINS:
            return JsonResponse({"error": "Unauthorized host"}, status=403)

        if referer and not any(ref in referer for ref in ALLOWED_ORIGINS):
            return JsonResponse({"error": "Unauthorized host"}, status=403)

        return self.get_response(request)
