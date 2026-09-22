import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Room, RoomMessage

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.room = await Room.objects.filter(room_id=self.room_id).afirst()

        # Присоединяемся к группе комнаты
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Покидаем группу. Ключи НЕ удаляем: комната и её участники
        # сохраняются, чтобы можно было вернуться в любой момент.
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Получение сообщения от клиента по WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        payload = data.get('payload')

        # Сохраняем в ящик комнаты: если адресат офлайн, заберёт при входе.
        # Храним только шифртекст — расшифровать его сервер не может.
        if self.room is not None and payload:
            await RoomMessage.objects.acreate(room=self.room, payload=payload)

        # Пересылаем зашифрованный blob всем участникам в этой комнате
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'payload': payload
            }
        )

    # Отправка сообщения обратно клиенту
    async def chat_message(self, event):
        payload = event['payload']
        await self.send(text_data=json.dumps({
            'payload': payload
        }))
