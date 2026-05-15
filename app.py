import threading
import uuid
from typing import Dict
from flask import Flask, request, jsonify, render_template
from crawler import WebCrawler

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024

tasks: Dict[str, dict] = {}
task_lock = threading.Lock()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/crawl', methods=['POST'])
def start_crawl():
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    keywords_raw = data.get('keywords') or ''
    max_depth = int(data.get('max_depth', 2))

    if isinstance(keywords_raw, str):
        keywords = [k.strip() for k in keywords_raw.split(',') if k.strip()]
    else:
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]

    if not url:
        return jsonify({'error': '请输入网站URL'}), 400
    if not keywords:
        return jsonify({'error': '请输入至少一个关键词'}), 400

    try:
        url = WebCrawler.validate_url(url)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    max_depth = max(1, min(max_depth, 4))

    task_id = str(uuid.uuid4())[:8]
    crawler = WebCrawler(max_depth=max_depth, max_pages=30, delay=0.3)

    with task_lock:
        tasks[task_id] = {
            'crawler': crawler,
            'status': 'running',
            'progress': crawler.progress,
        }

    def run():
        try:
            crawler.crawl(url, keywords)
        except Exception as e:
            with task_lock:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error'] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'task_id': task_id, 'status': 'started'})


@app.route('/api/status/<task_id>')
def get_status(task_id):
    with task_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({'error': '任务不存在'}), 404

        crawler: WebCrawler = task['crawler']
        return jsonify({
            'task_id': task_id,
            'status': crawler.progress['status'],
            'progress': crawler.progress,
            'results': crawler.results if crawler.progress['status'] in ('completed', 'error') else None,
        })


@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    with task_lock:
        return jsonify({
            'tasks': [
                {
                    'task_id': tid,
                    'status': t['crawler'].progress['status'],
                    'crawled': t['crawler'].progress['crawled'],
                    'message': t['crawler'].progress['message'],
                }
                for tid, t in tasks.items()
            ]
        })


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
