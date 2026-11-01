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
