from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
from PIL import Image
import os
import json
import base64


# Create your views here.
@csrf_exempt
def receive_snippet(request):
    if request.method == "POST":
        parsed_data = json.loads(request.body)
        base64_string = parsed_data.get("image_data")

        if not base64_string:
            return JsonResponse({"error": "No image data provided"}, status=400)

        if "," in base64_string:
            base64_string = base64_string.split(",")[1]

        bytes_decoded = base64.b64decode(base64_string)
        img = Image.open(BytesIO(bytes_decoded))
        out_jpg = img.convert("RGB")
        os.makedirs("./api/img/", exist_ok=True)
        out_jpg.save("./api/img/snippet.jpg")

        return JsonResponse({"message": "Image saved successfully!"}, status=200)
