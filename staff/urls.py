from django.urls import path
from . import views

app_name = 'staff'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.deposits, name='deposits'),
    path('deposits/', views.deposits, name='deposits'),
    path('withdrawals/', views.withdrawals, name='withdrawals'),
    path('api/deposits/<int:request_id>/approve/', views.api_approve_deposit, name='api_approve_deposit'),
    path('api/deposits/<int:request_id>/reject/', views.api_reject_deposit, name='api_reject_deposit'),
    path('api/withdrawals/<int:request_id>/approve/', views.api_approve_withdrawal, name='api_approve_withdrawal'),
    path('api/withdrawals/<int:request_id>/reject/', views.api_reject_withdrawal, name='api_reject_withdrawal'),
]
