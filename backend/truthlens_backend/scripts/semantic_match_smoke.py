import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "truthlens_backend.settings")
django.setup()

from api.models import Claim
from api.embedding_service import generate_embedding
from api.claim_matching import find_semantic_match

print("Testing Semantic Matching...")

def test_pair(t1, t2):
    print(f"\n--- Testing Pair ---")
    print(f"1: {t1}")
    print(f"2: {t2}")
    
    e1 = generate_embedding(t1)
    e2 = generate_embedding(t2)
    
    c = Claim.objects.create(claim_type="TEXT", context_text=t2, claim_embedding=e2)
    
    from pgvector.django import CosineDistance
    dist = Claim.objects.filter(id=c.id).annotate(distance=CosineDistance("claim_embedding", e1)).first().distance
    sim = 1 - dist
    print(f"Similarity: {sim:.4f}")
    c.delete()

test_pair("The president declared martial law today", "PBBM signed a martial law decree this morning")
test_pair("Fuel prices rising due to conflict in Middle East", "Gas costs expected to increase because of war in the Middle East")
test_pair("Rodrigo Duterte announces his candidacy for mayor in Davao City", "Former President Duterte will run for mayor of Davao")
test_pair("A magnitude 7.2 earthquake hit Metro Manila", "A strong 7.2 earthquake struck the capital region of the Philippines")
test_pair("A magnitude 7.2 earthquake hit Metro Manila", "A magnitude 5.0 earthquake hit Davao City")
