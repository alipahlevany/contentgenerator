from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Content, GenerationJob
from .serializers import ContentSerializer
from .services import generate_content
from .tasks import run_generation_job_task


class ContentListAPIView(generics.ListAPIView):
    queryset = Content.objects.all().order_by("-created_at")
    serializer_class = ContentSerializer


class GenerateContentAPIView(APIView):
    def post(self, request):
        title = request.data.get("title")
        prompt = request.data.get("prompt")

        if not title or not prompt:
            return Response(
                {"error": "title and prompt are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            generated_text = generate_content(prompt)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content = Content.objects.create(
            title=title,
            prompt=prompt,
            generated_content=generated_text,
            status="generated",
        )

        serializer = ContentSerializer(content)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


@api_view(["POST"])
def start_job_api(request, job_id):
    try:
        job = GenerationJob.objects.get(id=job_id)
    except GenerationJob.DoesNotExist:
        return Response(
            {
                "success": False,
                "message": "Job not found.",
            },
            status=404,
        )

    if job.status == "running":
        return Response(
            {
                "success": False,
                "message": "Job is already running.",
            },
            status=400,
        )

    job.status = "pending"
    job.should_stop = False
    job.error_message = ""
    job.generated_count = 0
    job.skipped_count = 0
    job.current_step = 0
    job.save()

    run_generation_job_task.delay(job.id)

    return Response(
        {
            "success": True,
            "job_id": job.id,
            "message": "Job started successfully.",
        }
    )


@api_view(["POST"])
def stop_job_api(request, job_id):
    try:
        job = GenerationJob.objects.get(id=job_id)
    except GenerationJob.DoesNotExist:
        return Response(
            {
                "success": False,
                "message": "Job not found.",
            },
            status=404,
        )

    job.should_stop = True
    job.save()

    return Response(
        {
            "success": True,
            "job_id": job.id,
            "message": "Stop requested.",
        }
    )


@api_view(["GET"])
def job_status_api(request, job_id):
    try:
        job = GenerationJob.objects.get(id=job_id)
    except GenerationJob.DoesNotExist:
        return Response(
            {
                "success": False,
                "message": "Job not found.",
            },
            status=404,
        )

    return Response(
        {
            "success": True,
            "id": job.id,
            "status": job.status,
            "count": job.count,
            "generated_count": job.generated_count,
            "skipped_count": job.skipped_count,
            "current_step": job.current_step,
            "error_message": job.error_message,
        }
    )