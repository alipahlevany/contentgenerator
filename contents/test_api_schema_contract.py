from django.test import TestCase
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient
from contents.models import Content, ExternalClient
from contents.api.serializers.system import APIErrorSerializer
from contents.api.serializers.export import ContentExportResponseSerializer


class SchemaContractTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def test_success_envelopes_and_client_auth_cover_all_routes(self):
        for path, methods in self.schema['paths'].items():
            if not path.startswith('/api/v1/'):
                continue
            for method, operation in methods.items():
                if method not in ('get', 'post'):
                    continue
                self.assertEqual(operation['security'], [] if path.endswith('/health/') else [{'ClientApiKey': []}], path)
                for code, response in operation['responses'].items():
                    if not code.startswith('2') or path.endswith('/delivery/'):
                        continue
                    body = response['content']['application/json']['schema']
                    self.assertEqual(set(body['required']), {'success', 'message', 'data'}, path)

    def test_reply_export_contract_matches_live_view_and_history(self):
        client = ExternalClient.objects.create(name='Schema client', code='schema-client', api_key='schema-test-key')
        reply = Content.objects.create(title='Reply', content_type='email_reply', prompt='p', generated_content='Hello', status='generated')
        api = APIClient()
        url = reverse('contents:api-reply-export')
        operation = self.schema['paths'][url]['post']
        self.assertTrue({'200', '400', '403', '409', '429'} <= set(operation['responses']))
        self.assertIn('Idempotency-Key', [p['name'] for p in operation['parameters']])
        first = api.post(url, {'count': 1}, format='json', HTTP_X_API_KEY='schema-test-key', HTTP_IDEMPOTENCY_KEY='batch-1')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['data']['items'][0]['id'], reply.pk)
        self.assertEqual(first.data['data']['client'], client.code)
        payload = ContentExportResponseSerializer(data=first.data['data'])
        self.assertTrue(payload.is_valid(), payload.errors)
        replay = api.post(url, {'count': 1}, format='json', HTTP_X_API_KEY='schema-test-key', HTTP_IDEMPOTENCY_KEY='batch-1')
        self.assertEqual(first.data, replay.data)
        next_batch = api.post(url, {'count': 1}, format='json', HTTP_X_API_KEY='schema-test-key', HTTP_IDEMPOTENCY_KEY='batch-2')
        self.assertEqual(next_batch.data['data']['items'], [])
        denied = api.post(url, {'count': 1}, format='json')
        self.assertEqual(denied.status_code, 403)
        error = APIErrorSerializer(data=denied.data)
        self.assertTrue(error.is_valid(), error.errors)

    def test_pagination_documents_both_response_shapes(self):
        for path in ('/api/v1/contents/', '/api/v1/generation-jobs/', '/api/v1/generation-jobs/reply/'):
            operation = self.schema['paths'][path]['get']
            data = operation['responses']['200']['content']['application/json']['schema']['properties']['data']
            self.assertEqual(data['oneOf'][0]['type'], 'array')
            self.assertIn('next_cursor', data['oneOf'][1]['properties'])
            self.assertTrue({'cursor', 'page_size'} <= {p['name'] for p in operation['parameters']})
