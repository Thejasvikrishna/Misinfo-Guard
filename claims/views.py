from rest_framework import viewsets
from .models import Claim
from .serializers import ClaimSerializer
from .tasks import process_claim_pipeline


class ClaimViewSet(viewsets.ModelViewSet):
    queryset = Claim.objects.all()
    serializer_class = ClaimSerializer

    def perform_create(self, serializer):
        claim = serializer.save()
        process_claim_pipeline.delay(claim.id)