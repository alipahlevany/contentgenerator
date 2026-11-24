"""Document the API's shared envelopes without changing response serialization."""
from copy import deepcopy

KEY_DESCRIPTION = (
    "Use the API key of the destination in Admin > External clients (for example zharik). "
    "This is not an OpenAI key. API and manual exports share this client's export history."
)


def envelope(data):
    return {"type": "object", "required": ["success", "message", "data"], "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "message": {"type": "string"}, "data": data,
    }}


def object_field(name, schema):
    return {"type": "object", "required": [name], "properties": {name: schema}}


def document_api_contract(result, generator, request, public):
    result["components"].setdefault("securitySchemes", {})["ClientApiKey"] = {
        "type": "apiKey", "in": "header", "name": "X-API-Key", "description": KEY_DESCRIPTION,
    }
    for path, operations in result["paths"].items():
        if not path.startswith('/api/v1/'):
            continue
        for method, operation in operations.items():
            if method not in ('get', 'post'):
                continue
            operation['security'] = [] if path.endswith('/health/') else [{'ClientApiKey': []}]
            operation['parameters'] = [p for p in operation.get('parameters', []) if p.get('name') != 'X-API-Key']
            responses = operation['responses']
            for code, response in list(responses.items()):
                if not code.startswith('2') or path.endswith('/delivery/'):
                    continue
                media = response.get('content', {}).get('application/json')
                if media is None:
                    continue
                data = deepcopy(media['schema'])
                if '/generation-jobs/' in path and not (method == 'get' and data.get('type') == 'array'):
                    data = object_field('job', {'$ref': '#/components/schemas/GenerationJob'})
                elif path.startswith('/api/v1/contents/{'):
                    data = object_field('content', data)
                if method == 'get' and data.get('type') == 'array':
                    data = {'oneOf': [data, {
                        'type': 'object', 'required': ['results', 'next_cursor'], 'properties': {
                            'results': deepcopy(data), 'next_cursor': {'type': 'string', 'nullable': True},
                        },
                    }]}
                    operation['parameters'] += [
                        {'name': 'page_size', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'description': 'Enables cursor pagination. Without pagination parameters, data is an array of up to 100 items.'},
                        {'name': 'cursor', 'in': 'query', 'schema': {'type': 'string'}, 'description': 'Use next_cursor from the previous page; cursors expire after 24 hours.'},
                    ]
                    responses.setdefault('400', {'description': 'Invalid cursor or page size.', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/APIError'}}}})
                media['schema'] = envelope(data)
                for example in media.get('examples', {}).values():
                    if 'value' in example and 'success' not in example['value']:
                        example['value'] = {'success': True, 'message': 'Request completed successfully.', 'data': example['value']}
            for code, response in responses.items():
                if code.startswith('4'):
                    response.setdefault('content', {'application/json': {'schema': {'$ref': '#/components/schemas/APIError'}}})
            idempotent = method == 'post' and (path.endswith('/export/') or path.endswith('/delivery/') or ('/generation-jobs/' in path and '{' not in path))
            if idempotent:
                operation["parameters"] = [p for p in operation["parameters"] if p["name"] != "Idempotency-Key"]
                operation['parameters'].append({
                    'name': 'Idempotency-Key', 'in': 'header', 'required': False,
                    'schema': {'type': 'string', 'maxLength': 255, 'pattern': r'^[A-Za-z0-9._:-]{1,255}$'},
                    'description': 'Use a new key for each new batch. Retry the same body and key to replay its saved response for 24 hours, without exporting another batch. A changed body with the same key returns 409. Missing or invalid keys do not enable replay protection.',
                })
                responses['409'] = {'description': 'Idempotency key reused with a different request.', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/APIError'}}}}
            if path.endswith('/export/'):
                responses['429'] = {'description': 'Daily export quota exceeded.', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/APIError'}}}}
                operation['description'] = operation.get('description', '') + '\n\nPull-based export: no generation or automatic delivery is triggered. Results are in data.items; reply text is generated_content. Successful versions are recorded for the API-key client and skipped by future new batches, including manual CSV/JSON downloads. No available items returns HTTP 200 with exported=0 and items=[]. A retry with the same valid Idempotency-Key intentionally replays the original batch.'
                if path.endswith('/replies/export/'):
                    operation['requestBody']['content']['application/json']['examples'] = {'ReplyBatch': {'summary': 'Get up to 100 replies for the API-key client', 'value': {'count': 100, 'languages': 'all'}}}
    return result
