from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.overview, name='overview'),
    path('players/', views.players, name='players'),
    path('rooms/', views.rooms, name='rooms'),
    path('rooms/<str:room_code>/', views.room_detail, name='room_detail'),
    path('live/', views.live_games, name='live'),
    path('transactions/', views.transactions, name='transactions'),
    path('logs/', views.logs, name='logs'),
    path('api/players/<int:player_id>/add-coins/', views.api_add_coins, name='api_add_coins'),
    path('api/players/<int:player_id>/deduct-coins/', views.api_deduct_coins, name='api_deduct_coins'),
    path('api/players/<int:player_id>/reset-coins/', views.api_reset_coins, name='api_reset_coins'),
    path('api/players/<int:player_id>/ban/', views.api_ban_player, name='api_ban_player'),
    path('api/players/<int:player_id>/kick/<str:room_code>/', views.api_kick_player, name='api_kick_player'),
    path('api/rooms/<str:room_code>/close/', views.api_force_close_room, name='api_force_close'),
    path('api/rooms/<str:room_code>/live-state/', views.api_room_live_state, name='api_live_state'),
]
