from django.contrib import admin
from .models import Room, RoomKey, RoomMessage


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'created_at')
    search_fields = ('room_id',)


@admin.register(RoomKey)
class RoomKeyAdmin(admin.ModelAdmin):
    list_display = ('room', 'participant', 'public_key', 'created_at')
    list_filter = ('participant',)


@admin.register(RoomMessage)
class RoomMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'payload', 'created_at')
    # payload — шифртекст, сервер не может его расшифровать
