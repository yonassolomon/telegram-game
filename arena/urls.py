from django.urls import path
from . import views

app_name = 'arena'

urlpatterns = [
    path('', views.lobby, name='lobby'),
    path('api/<int:round_id>/select-card/', views.api_select_card, name='api_select_card'),
    path('api/<int:round_id>/leave/', views.api_leave_arena, name='api_leave_arena'),
    path('api/<int:round_id>/state/', views.api_round_state, name='api_round_state'),
    path('api/card/<int:card_number>/', views.api_card_preview, name='api_card_preview'),
]
