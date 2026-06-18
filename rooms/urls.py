from django.urls import path
from . import views

urlpatterns = [
    path('', views.RoomListCreateView.as_view(), name='room-list-create'),
    path('<str:code>/', views.RoomDetailView.as_view(), name='room-detail'),
    path('<str:code>/join/', views.JoinRoomView.as_view(), name='room-join'),
    path('<str:code>/leave/', views.LeaveRoomView.as_view(), name='room-leave'),
    path('<str:code>/mute/<str:email>/', views.MuteParticipantView.as_view(), name='room-mute'),
]