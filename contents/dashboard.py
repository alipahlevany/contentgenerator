from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET


@staff_member_required
def operations_dashboard(request):
    return redirect("admin:index")


@staff_member_required
@require_GET
def dashboard_metrics(request):
    from contents.admin.intelligence_dashboard import cached_dashboard_metrics
    response = JsonResponse(cached_dashboard_metrics(request.GET.get("days", 7)))
    response['Cache-Control'] = 'private, no-store'
    return response


@staff_member_required
@require_GET
def openai_account_usage(request):
    # Organization-wide usage can include projects outside this application.
    if not request.user.is_superuser:
        response = JsonResponse({"detail": "Administrator access required."}, status=403)
    else:
        from contents.openai_usage import get_openai_usage
        response = JsonResponse(get_openai_usage(request.GET.get("days", 7)))
    response['Cache-Control'] = 'private, no-store'
    return response
