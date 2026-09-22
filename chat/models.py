from django.db import models

class Room(models.Model):
    room_id = models.CharField(max_length=16, unique=True)  # Код комнаты (например, "1234")
    created_at = models.DateTimeField(auto_now_add=True)

class RoomKey(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='keys')
    participant = models.CharField(max_length=1)  # 'A' или 'B'
    public_key = models.TextField()  # Публичный ключ X25519 (в hex или base64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('room', 'participant')

class RoomMessage(models.Model):
    """Ящик недоставленных сообщений: сервер хранит только шифртекст
    (base64 iv||hmac||ct) и не может его расшифровать. Сообщения выдаются
    участнику при входе (fetch) и удаляются — доставка ровно один раз."""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    payload = models.TextField()  # Шифртекст, как есть из WebSocket
    created_at = models.DateTimeField(auto_now_add=True)
