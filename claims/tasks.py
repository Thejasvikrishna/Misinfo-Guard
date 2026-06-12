import os
import pytesseract
from celery import shared_task
from django.conf import settings
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


import os
import pytesseract
from celery import shared_task
from django.conf import settings
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


@shared_task
def process_claim_pipeline(claim_id):
    # --- Late imports to ensure Django ORM and .env are fully loaded ---
    from .models import Claim, Evidence, Verdict
    from .ai_engine import MisinfoEngine

    claim = Claim.objects.get(id=claim_id)
    claim.status = 'PROCESSING'
    claim.save()
    
    try:
        text = claim.claim_text
        
        # 1. OCR Extraction
        if claim.image and not text:
            raw_text = pytesseract.image_to_string(Image.open(claim.image.path))
            # NEW: Clean the OCR text before doing anything else!
            text = engine.clean_claim_text(raw_text)
            
            # Save the clean text back to the database so the user can see what was analyzed
            claim.claim_text = text 
            claim.save()
        
        # 2. Get Evidence using the CLEANED text
        evidence = engine.get_top_evidence(text)
        
        # 3. Get AI Verdict
        result = engine.call_ai_judge(text, evidence)
        
        # 4. Save results
        claim.stance = result.get('stance')
        claim.explanation = result.get('explanation')
        claim.confidence = result.get('confidence')
        claim.sources = result.get('sources', [])
        claim.status = 'COMPLETED'
        
    except Exception as e:
        claim.status = 'ERROR'
        claim.explanation = str(e)
    
    claim.save()

    # --------------------------------------------------------
    # STEP 1: OCR — extract text from image if claim is image
    # --------------------------------------------------------
    if hasattr(claim, 'image') and claim.image:
        try:
            text_from_img = pytesseract.image_to_string(Image.open(claim.image.path))
            extracted = text_from_img.strip()
            if extracted:
                claim.claim_text = extracted
                claim.save()
                print(f"📷 OCR extracted: {claim.claim_text[:80]}")
            else:
                print("⚠️ OCR returned empty text")
        except Exception as e:
            print(f"❌ OCR ERROR: {str(e)}")

    if not claim.claim_text or not claim.claim_text.strip():
        print("❌ No claim text — aborting pipeline")
        claim.status = 'COMPLETED'
        claim.save()
        return