from django.db import models

class Claim(models.Model):
    TYPES = [('text', 'Text'), ('image', 'Image'), ('url', 'URL')]
    STATUS = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('ERROR', 'Error'),
    ]

    is_correct = models.BooleanField(null=True, blank=True)
    claim_text = models.TextField(blank=True, null=True)
    sources = models.JSONField(default=list)
    claim_type = models.CharField(max_length=20)
    image = models.ImageField(upload_to='claims/', null=True, blank=True)
    status = models.CharField(max_length=20, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    timeframe = models.CharField(max_length=20, default='current')
    class Evidence(models.Model):
    claim = models.ForeignKey(
        Claim,
        related_name='evidences',
        on_delete=models.CASCADE
    )
    source_url = models.TextField(default='unknown')
    text = models.TextField()
    score = models.FloatField()