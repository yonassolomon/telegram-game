from django.urls import path
from . import views

app_name = 'webapp'

urlpatterns = [
    path('', views.home, name='home'),
    path('phone/', views.submit_phone, name='submit_phone'),
    path('rooms/', views.rooms, name='rooms'),
    path('my-rooms/', views.my_rooms, name='my_rooms'),
    path('rooms/create/', views.create_room, name='create_room'),
    path('rooms/join/', views.join_private, name='join_private'),
    path('room/<str:room_code>/', views.room, name='room'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('wallet/', views.wallet, name='wallet'),
    path('daily/', views.daily, name='daily'),
    path('daily/claim/', views.claim_daily, name='claim_daily'),
    path('api/room/<str:room_code>/join/', views.api_join_room, name='api_join'),
    path('api/room/<str:room_code>/leave/', views.api_leave_room, name='api_leave'),
    path('api/room/<str:room_code>/start/', views.api_start_game, name='api_start'),
    path('api/room/<str:room_code>/state/', views.api_room_state, name='api_state'),
    path('api/room/<str:room_code>/info/', views.api_room_info, name='api_info'),
    path('api/set-language/', views.set_language, name='set_language'),
    path('api/claim-daily/', views.api_claim_daily, name='api_claim_daily'),
    path('help/', views.help_page, name='help_page'),
]
