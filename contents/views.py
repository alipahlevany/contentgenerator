from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Content
from .serializers import ContentSerializer
from .services import generate_content


class ContentListAPIView(generics.ListAPIView):
    queryset = Content.objects.all().order_by('-created_at')
    serializer_class = ContentSerializer


class GenerateContentAPIView(APIView):
    def post(self, request):
        title = request.data.get('title')
        prompt = request.data.get('prompt')

        if not title or not prompt:
            return Response(
                {'error': 'title and prompt are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            generated_text = generate_content(prompt)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        content = Content.objects.create(
            title=title,
            prompt=prompt,
            generated_content=generated_text,
            status='generated',
        )

        serializer = ContentSerializer(content)
        return Response(serializer.data, status=status.HTTP_201_CREATED)