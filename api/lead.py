"""
Pipedrive Lead Proxy — Receives form submissions from Long Drive sites
and creates Person + Organization + Deal in the correct pipeline.
Deploy to Vercel. Set PIPEDRIVE_API_TOKEN in Vercel Environment Variables.
"""
import json, os, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler

API_TOKEN = os.environ.get('PIPEDRIVE_API_TOKEN', '')
BASE = 'https://api.pipedrive.com/v1'

# Pipeline IDs
PIPELINES = {
    'lds': 2,
    'ldm': 1,
    'ldp': 3,
}

# Custom field keys (from setup)
FIELD_KEYS = {
    'lead_source': '9c107343e885b33d0227e8c1debdef72a0f6410a',
    'service_need': '508948e6e7b532d90d201d99f062ced2034c69c7',
    'role': '985df4be22fe7cf93d47fac0e83848b466e56974',
    'timeline': 'e15b6fe0c06cf4265cb68a9c0d1b91332e7328c3',
    'message': '4ac5e754fa1a15687ed52b3ebae3c192f9284395',
}

ALLOWED_ORIGINS = [
    'https://longdrivestrategy.com',
    'https://www.longdrivestrategy.com',
    'https://longdrivemarketing.com',
    'https://www.longdrivemarketing.com',
    'https://longdrivepartners.com',
    'https://www.longdrivepartners.com',
    'https://radish-wolf-y8bb.squarespace.com',  # LDS dev
    'https://carrot-elk-xmaj.squarespace.com',   # LDM dev
]

def pipedrive(endpoint, body):
    url = f'{BASE}{endpoint}?api_token={API_TOKEN}'
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())

def cors_headers(origin):
    h = {
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
    }
    if origin in ALLOWED_ORIGINS:
        h['Access-Control-Allow-Origin'] = origin
    return h

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        origin = self.headers.get('Origin', '')
        self.send_response(200)
        for k, v in cors_headers(origin).items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        origin = self.headers.get('Origin', '')
        headers = cors_headers(origin)

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))

            name = body.get('name', '').strip()
            email = body.get('email', '').strip()
            phone = body.get('phone', '').strip()
            org_name = body.get('organization', '').strip()
            role = body.get('role', '')
            service_need = body.get('service_need', body.get('topic', ''))
            timeline = body.get('timeline', '')
            message = body.get('message', body.get('brief', ''))
            source = body.get('source', 'Unknown')
            pipeline_key = body.get('pipeline', 'lds')

            if not name or not email:
                self._respond(400, headers, {'error': 'Name and email required'})
                return

            pipeline_id = PIPELINES.get(pipeline_key, 2)

            # 1. Create Person
            person_data = {'name': name, 'email': [email]}
            if phone:
                person_data['phone'] = [phone]
            person = pipedrive('/persons', person_data)
            person_id = person['data']['id'] if person.get('success') else None

            # 2. Create Organization (if provided)
            org_id = None
            if org_name:
                org = pipedrive('/organizations', {'name': org_name})
                org_id = org['data']['id'] if org.get('success') else None

            # 3. Create Deal
            deal_title = f'{source}: {name}'
            if org_name:
                deal_title += f' ({org_name})'

            deal_data = {
                'title': deal_title,
                'pipeline_id': pipeline_id,
                FIELD_KEYS['lead_source']: source,
            }
            if person_id:
                deal_data['person_id'] = person_id
            if org_id:
                deal_data['org_id'] = org_id
            if service_need:
                deal_data[FIELD_KEYS['service_need']] = service_need
            if role:
                deal_data[FIELD_KEYS['role']] = role
            if timeline:
                deal_data[FIELD_KEYS['timeline']] = timeline
            if message:
                deal_data[FIELD_KEYS['message']] = message

            deal = pipedrive('/deals', deal_data)

            if deal.get('success'):
                self._respond(200, headers, {
                    'success': True,
                    'deal_id': deal['data']['id'],
                    'message': 'Lead captured successfully'
                })
            else:
                self._respond(500, headers, {'error': 'Failed to create deal', 'details': deal})

        except Exception as e:
            self._respond(500, headers, {'error': str(e)})

    def _respond(self, status, headers, body):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
