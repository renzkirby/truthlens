from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .tasks import snippet_fact_check_process
from .services import process_image


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

        # Decode the base64 string and save it as an image
        image_hash, _ = process_image(base64_string)
        print("IMAGE HASH:", image_hash)

        # Save Claim to db
        # -- Code to save the claim and get claim_id goes here (not implemented) ---
        claim_id = None  # Placeholder for claim ID after saving to DB

        snippet_fact_check_process.delay(image_hash, base64_string, claim_id=None)

        # TO DO: Return the actual claim_id after saving the claim to the database, so that the frontend can use it to fetch results later when users view the claim details.

        return JsonResponse(
            {"claim_id": claim_id},
            status=200,
        )
