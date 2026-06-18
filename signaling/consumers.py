import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rooms.models import Room, Participant

User = get_user_model()


class RoomConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'room_{self.room_code}'
        self.user = None
        self.authenticated = False

        
        await self.accept()

    async def disconnect(self, close_code):
        if not self.authenticated:
            return

        await self.remove_channel_name()
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

        # --- gate everything behind authentication ---
        if not self.authenticated:
            if message_type != 'authenticate':
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'You must authenticate first'
                }))
                await self.close()
                return

            await self.handle_authenticate(data)
            return

        # everything below only runs once authenticated 

        target_user = data.get('target')

        if message_type in ('offer', 'answer', 'ice_candidate'):
            if not target_user:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'target is required for signaling messages'
                }))
                return

            target_channel = await self.get_channel_name(target_user)

            if not target_channel:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'{target_user} is not connected'
                }))
                return

            await self.channel_layer.send(
                target_channel,
                {
                    'type': 'signaling_message',
                    'payload': data,
                    'sender': self.user.email,
                }
            )

        elif message_type == 'get_participants':
            participants = await self.get_active_participants()
            await self.send(text_data=json.dumps({
                'type': 'participants_list',
                'participants': participants,
            }))

        elif message_type == 'mute':
            target_user = data.get('target')
            if not target_user:
                return

            room_obj = await self.get_room()
            is_room_host = await self.check_is_host(room_obj)
            if not is_room_host:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Only the host can mute participants'
                }))
                return

            target_channel = await self.get_channel_name(target_user)
            if target_channel:
                await self.channel_layer.send(
                    target_channel,
                    {
                        'type': 'muted',
                        'by': self.user.email,
                    }
                )

    # authentication handler

    async def handle_authenticate(self, data):
        token = data.get('token')

        if not token:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'token is required'
            }))
            await self.close()
            return

        user = await self.get_user_from_token(token)

        if user is None:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid or expired token'
            }))
            await self.close()
            return

        room_exists = await self.get_room()
        if not room_exists:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room not found'
            }))
            await self.close()
            return

        # auth succeeded — now do everything connect() used to do
        self.user = user
        self.authenticated = True

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.store_channel_name()
        await self.mark_participant_active()

        await self.send(text_data=json.dumps({
            'type': 'authenticated',
            'user': self.user.email,
        }))

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user': self.user.email,
            }
        )

    # event handlers 

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

    async def muted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'muted',
            'by': event['by'],
        }))

    # redis helpers

    async def store_channel_name(self):
        key = f'channel_{self.room_code}_{self.user.email}'
        await cache.aset(key, self.channel_name, timeout=86400)

    async def get_channel_name(self, user_email):
        key = f'channel_{self.room_code}_{user_email}'
        return await cache.aget(key)

    async def remove_channel_name(self):
        key = f'channel_{self.room_code}_{self.user.email}'
        await cache.adelete(key)



    # database helpers 

    @database_sync_to_async
    def get_room(self):
        try:
            return Room.objects.get(code=self.room_code, is_active=True)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        try:
            token = AccessToken(token_key)
            user_id = token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return None

    @database_sync_to_async
    def get_active_participants(self):
        participants = Participant.objects.filter(
            room__code=self.room_code,
            is_active=True
        ).select_related('user')
        return [p.user.email for p in participants]

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

    @database_sync_to_async
    def check_is_host(self, room):
        return room.host == self.user