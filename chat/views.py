import secrets
from functools import wraps

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Room, RoomKey, RoomMessage


def bot_only(view_func):
    """Доступ только для Telegram-бота: требует заголовок X-Bot-Token."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.headers.get('X-Bot-Token', '') != settings.BOT_API_TOKEN:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return view_func(request, *args, **kwargs)
    return wrapper


@api_view(['POST'])
@bot_only
def create_room(request):
    room_id = ''.join(secrets.choice('23456789ABCDEFGHJKMNPQRSTVWXYZ') for _ in range(8))
    while Room.objects.filter(room_id=room_id).exists():
        room_id = ''.join(secrets.choice('23456789ABCDEFGHJKMNPQRSTVWXYZ') for _ in range(8))
    
    Room.objects.create(room_id=room_id)
    return Response({'room_id': room_id}, status=status.HTTP_201_CREATED)

@api_view(['POST'])
def join_room(request, room_id):
    try:
        room = Room.objects.get(room_id=room_id)
    except Room.DoesNotExist:
        return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
    
    public_key = request.data.get('public_key')
    if not public_key:
        return Response({'error': 'public_key is required'}, status=status.HTTP_400_BAD_REQUEST)

    existing_keys = RoomKey.objects.filter(room=room)

    # Повторный вход участника с тем же ключом — обновляем, а не отклоняем
    existing = existing_keys.filter(public_key=public_key).first()
    if existing:
        participant = existing.participant
    else:
        if existing_keys.count() >= 2:
            return Response({'error': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)
        participant = 'A' if existing_keys.count() == 0 else 'B'
        RoomKey.objects.create(room=room, participant=participant, public_key=public_key)

    other_key_obj = RoomKey.objects.filter(room=room).exclude(participant=participant).first()
    other_key = other_key_obj.public_key if other_key_obj else None

    return Response({
        'status': 'joined',
        'participant': participant,
        'other_public_key': other_key
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
def room_keys(request, room_id):
    """Отдаёт все публичные ключи комнаты — клиент выбирает чужой.
    Нужен первому участнику: при его входе собеседника ещё нет,
    и join не может вернуть чужой ключ."""
    try:
        room = Room.objects.get(room_id=room_id)
    except Room.DoesNotExist:
        return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

    keys = [k.public_key for k in RoomKey.objects.filter(room=room)]
    return Response({'public_keys': keys}, status=status.HTTP_200_OK)


@api_view(['POST'])
def fetch_messages(request, room_id):
    """Ящик недоставленных сообщений: отдаём накопившийся шифртекст
    и удаляем его. Доставка ровно один раз; если клиент успел получить
    сообщение по WebSocket, он отсеет дубль по своей локальной истории.
    Сами сообщения недоступны для расшифровки серверу."""
    try:
        room = Room.objects.get(room_id=room_id)
    except Room.DoesNotExist:
        return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

    inbox = RoomMessage.objects.filter(room=room).order_by('created_at')
    messages = list(inbox.values_list('payload', flat=True))
    inbox.delete()
    return Response({'messages': messages}, status=status.HTTP_200_OK)
