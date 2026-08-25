from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from contents.admin.intelligence_dashboard import (
    get_dashboard_metrics,
    get_intelligence_context,
)


@staff_member_required
def operations_dashboard(request):
    return render(
        request,
        "dashboard/index.html",
        {
            "dashboard_metrics": get_dashboard_metrics(),
            **get_intelligence_context(),
        },
    )
