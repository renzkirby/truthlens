from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
from PIL import Image
import os
import json
import base64
import easyocr
import cv2
from dotenv import load_dotenv
from tavily import TavilyClient

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

        image_file = "./api/img/snippet.jpg"

        # ACCURACY PROBLEM WITH OPENCV
        # image_cv = cv2.imread(image_file)

        # # converts image's color to gray
        # gray_image = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)

        # # reduce image noise
        # thresh_img = cv2.adaptiveThreshold(
        #     gray_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        # )

        # cv2.imwrite("./api/img/processed_snippet.jpg", thresh_img)

        reader = easyocr.Reader(["en", "tl"])
        result = reader.readtext(image_file)


        for item in result:
            extracted_text = " ".join([item[1] for item in result])


        client = TavilyClient(os.environ.get("TAVILY_API_KEY"))

        response = client.search(
            query=extracted_text,
            search_depth="advanced"
        )

        return JsonResponse(
            {
                "message": "Image saved successfully!",
                "extracted_text": extracted_text,
                "result": response,
            },
            status=200,
        )
