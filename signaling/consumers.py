import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rooms.models import Room, Participant


class RoomConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'room_{self.room_code}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        room_exists = await self.get_room()
        if not room_exists:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.mark_participant_active()
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user': self.user.email,
            }
        )

    async def disconnect(self, close_code):
        await self.mark_participant_inactive()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user': self.user.email,
            }
        )

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type in ('offer', 'answer', 'ice_candidate'):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'signaling_message',
                    'payload': data,
                    'sender': self.user.email,
                }
            )

    # --- event handlers ---

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user': event['user'],
        }))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'user': event['user'],
        }))

    async def signaling_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'signaling_message',
            'payload': event['payload'],
            'sender': event['sender'],
        }))

    # --- database helpers ---

    @database_sync_to_async
    def get_room(self):
        try:
            return Room.objects.get(code=self.room_code, is_active=True)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def mark_participant_active(self):
        room = Room.objects.get(code=self.room_code, is_active=True)
        Participant.objects.update_or_create(
            room=room,
            user=self.user,
            defaults={'is_active': True}
        )

    @database_sync_to_async
    def mark_participant_inactive(self):
        Participant.objects.filter(
            room__code=self.room_code,
            user=self.user
        ).update(is_active=False)