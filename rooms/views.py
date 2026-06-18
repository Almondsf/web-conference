from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Room, Participant
from .serializers import RoomSerializer, CreateRoomSerializer
from django.shortcuts import get_object_or_404

def is_host(user, room):
    return room.host == user

class RoomListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        rooms = Room.objects.filter(is_active=True, participants__user=request.user)
        serializer = RoomSerializer(rooms, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        serializer = CreateRoomSerializer(data=request.data)
        if serializer.is_valid():
            room = serializer.save(host=request.user)
            return Response(RoomSerializer(room).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
class RoomDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, code):
        room = get_object_or_404(Room, code=code, is_active=True, participants__user=request.user)
        serializer = RoomSerializer(room)
        return Response(serializer.data)
    
    def delete(self, request, code):
        room = get_object_or_404(Room, code=code, host=request.user)
        if room.host != request.user:
            return Response(
                {'error': 'Only the host can close this room'},
                status=status.HTTP_403_FORBIDDEN
            )
        room.is_active = False
        room.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

class JoinRoomView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post (self, request, code):
        room = get_object_or_404(Room, code=code, is_active=True)
        
        active_participants = room.participants.filter(is_active=True).count()
        
        if active_participants >= room.max_participants:
            return Response(
                {'error': 'This room is full'},
                status=status.HTTP_403_FORBIDDEN
            )
        participant, created = Participant.objects.get_or_create(
            room=room, user=request.user, 
            defaults={'is_active': True}
        )
        
        if not created:
            participant.is_active = True
            participant.save()

        return Response(RoomSerializer(room).data)

class LeaveRoomView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, code):
        room = get_object_or_404(Room, code=code)
        participant = get_object_or_404(Participant, room=room, user=request.user)
        participant.is_active = False
        participant.save()
        return Response({'message': 'Left room successfully'})

class MuteParticipantView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, code, email):
        room = get_object_or_404(Room, code=code, is_active=True)

        if not is_host(request.user, room):
            return Response(
                {'error': 'Only the host can mute participants'},
                status=status.HTTP_403_FORBIDDEN
            )

        User = get_user_model()
        target = get_object_or_404(User, email=email)
        participant = get_object_or_404(
            Participant, room=room, user=target, is_active=True
        )
        participant.is_muted = True
        participant.save()

        return Response({'message': f'{email} has been muted'})