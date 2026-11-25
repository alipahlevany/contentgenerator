from copy import deepcopy
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django import template

register = template.Library()


_GROUPS = (
    {
        "key": "greeting",
        "name": "Greeting",
        "models": {
            "Greeting": "Greetings",
            "GreetingGenerationSettings": "Greeting settings",
        },
        "job_type": "greeting",
        "job_label": "Greeting generation jobs",
        "export_type": "greeting",
    },
    {
        "key": "replies",
        "name": "Replies",
        "models": {
            "EmailReply": "Generated replies",
            "ReplyGenerationSettings": "Reply settings",
            "ReplyContentExport": "Reply export history",
        },
        "job_type": "email_reply",
        "job_label": "Reply generation jobs",
    },
    {
        "key": "standard",
        "name": "Standard",
        "models": {
            "Content": "Standard content",
            "StandardGenerationSettings": "Standard settings",
        },
        "job_type": "standard",
        "job_label": "Standard generation jobs",
        "export_type": "standard",
    },
    {
        "key": "templates",
        "name": "Templates",
        "models": {
            "WarmupTemplate": "Warmup templates",
            "WarmupTemplateGenerationSettings": "Template settings",
        },
    },
)


def _with_query(url, **params):
    if not url:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _model_group_link(model, *, name, query=None):
    link = deepcopy(model)
    link["name"] = name
    if query and link.get("admin_url"):
        link["admin_url"] = _with_query(link["admin_url"], **query)
    return link


@register.simple_tag
def grouped_generation_apps(app_list):
    """Return the admin models arranged into their generation sections."""
    apps = deepcopy(app_list or [])
    contents_app = next(
        (app for app in apps if app.get("app_label") == "contents"),
        None,
    )
    if not contents_app:
        return apps

    by_object_name = {
        model.get("object_name"): model
        for model in contents_app.get("models", [])
    }
    assigned = set()
    grouped = []

    for group in _GROUPS:
        models = []
        for object_name, label in group["models"].items():
            model = by_object_name.get(object_name)
            if model:
                models.append(_model_group_link(model, name=label))
                assigned.add(object_name)

        job = by_object_name.get("GenerationJob")
        if job and group.get("job_type"):
            models.append(
                _model_group_link(
                    job,
                    name=group["job_label"],
                    query={"generation_type__exact": group["job_type"]},
                )
            )
            assigned.add("GenerationJob")

        exports = by_object_name.get("ContentExport")
        if exports and group.get("export_type"):
            models.append(
                _model_group_link(
                    exports,
                    name=f"{group['name']} export history",
                    query={"content__content_type__exact": group["export_type"]},
                )
            )
            assigned.add("ContentExport")

        if models:
            grouped.append(
                {
                    "app_label": f"contents_{group['key']}",
                    "name": group["name"],
                    "app_url": "",
                    "has_module_perms": True,
                    "models": models,
                }
            )

    remaining = [
        model for model in contents_app.get("models", [])
        if model.get("object_name") not in assigned
    ]
    result = []
    inserted = False
    for app in apps:
        if app is contents_app:
            result.extend(grouped)
            if remaining:
                other = deepcopy(contents_app)
                other["name"] = "Shared generation tools"
                other["app_url"] = ""
                other["models"] = remaining
                result.append(other)
            inserted = True
        else:
            result.append(app)
    return result if inserted else apps
