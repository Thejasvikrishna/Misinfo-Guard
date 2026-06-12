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
        from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, action
from django.shortcuts import render


@api_view(['POST'])
def submit_feedback(request, claim_id):
    try:
        claim = Claim.objects.get(id=claim_id)
        claim.is_correct = request.data.get('feedback')
        claim.save()
        return Response({"status": "Feedback recorded"})
    except Claim.DoesNotExist:
        return Response({"error": "Claim not found"}, status=404)


def home(request):
    return render(request, 'verifier/index.html')


class ClaimViewSet(viewsets.ModelViewSet):
    queryset = Claim.objects.all()
    serializer_class = ClaimSerializer

    @action(detail=True, methods=['post'], url_path='feedback')
    def feedback(self, request, pk=None):
        claim = self.get_object()

        feedback_value = request.data.get('is_correct')

        if feedback_value is None:
            return Response(
                {"error": "Field 'is_correct' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        claim.is_correct = bool(feedback_value)
        claim.save()

        return Response({
            "status": "Feedback recorded successfully",
            "claim_id": claim.id,
            "is_correct": claim.is_correct
        }, status=status.HTTP_200_OK)