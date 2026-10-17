"""Prevent durable ledger history from re-executing expired/completed web jobs."""

def queue_job_pending(order_text, prefix, door, token):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse

    spec = json.loads(order_text.split(prefix, 1)[1])
    job_id = spec.get('job_id')
    if not job_id:
        return False
    query = urllib.parse.urlencode({'token': token, 'job_id': job_id})
    request = urllib.request.Request(
        door + '/v1/tools/web.result?' + query,
        headers={'User-Agent': 'omniroute-kaggle-worker'},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            job = json.loads(response.read(200000).decode('utf-8'))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise
    return job.get('job_id') == job_id and job.get('status') in (
        'pending', 'queued', 'queued_cold_harvest', 'healing_in_playwright',
    )
