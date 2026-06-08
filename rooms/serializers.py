from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Room, Participant

User = get_user_model()

class ParticipantSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Participant
        fields = ('id', 'user_email', 'is_active', 'joined_at')

class RoomSerializer(serializers.ModelSerializer):
    host_email = serializers.EmailField(source='host.email', read_only=True)
    participants = ParticipantSerializer(many=True, read_only=True)
    participant_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Room
        fields = (
            'id', 'name', 'code', 'host_email',
            'is_active', 'max_participants',
            'participant_count', 'participants',
            'created_at',
        )
        read_only_fields = ('id', 'code', 'host_email', 'created_at')
    
    def get_participant_count(self, obj):
        return obj.participants.filter(is_active=True).count()

class CreateRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ('name', 'max_participants', 'password')