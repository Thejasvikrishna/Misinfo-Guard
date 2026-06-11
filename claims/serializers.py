from rest_framework import serializers
from .models import Claim

class ClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = [
            'id',
            'claim_text',
            'image',
            'claim_type',
            'status',
            'created_at'
        ]