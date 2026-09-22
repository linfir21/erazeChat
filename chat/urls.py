from django.urls import path
from .views import create_room, join_room, room_keys, fetch_messages

urlpatterns = [
    path('room/create/', create_room, name='create_room'),
    path('room/<str:room_id>/join/', join_room, name='join_room'),
    path('room/<str:room_id>/keys/', room_keys, name='room_keys'),
    path('room/<str:room_id>/messages/fetch/', fetch_messages, name='fetch_messages'),
]
