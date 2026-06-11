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
        from rest_framework import serializers
from .models import Claim, Evidence, Verdict

class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = ['id', 'source_url', 'text', 'score']

class VerdictSerializer(serializers.ModelSerializer):
    class Meta:
        model = Verdict
        fields = ['stance', 'explanation', 'confidence']

class ClaimSerializer(serializers.ModelSerializer):
    evidences = EvidenceSerializer(many=True, read_only=True)
    verdict = VerdictSerializer(read_only=True)

    class Meta:
        model = Claim
        fields = [
            'id',
            'claim_text',
            'image',
            'claim_type',
            'status',
            'evidences',
            'verdict',
            'created_at'
        ]