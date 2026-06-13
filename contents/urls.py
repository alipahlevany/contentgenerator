from django.urls import path
from .views import ContentListAPIView, GenerateContentAPIView

urlpatterns = [
    path('contents/', ContentListAPIView.as_view(), name='content-list'),
    path('generate-content/', GenerateContentAPIView.as_view(), name='generate-content'),
]