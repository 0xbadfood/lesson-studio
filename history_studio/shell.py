"""The learn.photovault.live shell: one entry to every studio (user, 2026-10-24).

Each studio is served under its slug on the same host (/physics/, /humanities/ ...): the master's Caddy strips the
prefix and proxies to the studio's own port, and the studios use relative URLs, so they run unchanged there and on
their own subdomains. Each studio keeps its own access code for now; the subdomains are retired later.
"""
import argparse
import html
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from . import catalog

HERE = Path(__file__).resolve().parent
ORDER = ['physics', 'chemistry', 'biology', 'maths', 'history', 'geography']
ABOUT = {'physics': 'Class 6-12 physics concept films, and Solve for JEE questions',
         'chemistry': 'Class 6-12 chemistry, with exact code-drawn structures',
         'biology': 'Class 6-12 biology, with the diagram library',
         'maths': 'Class 11-12 maths concept films',
         'history': 'History and the social science books',
         'geography': 'Geography, from the Class 6 books to Class 12'}


def page():
    cards = ''.join(
        f'<a class="studio" href="{p["slug"]}/"><span class="mark">{p["mark"]}</span>'
        f'<span><b>{html.escape(p["name"])}</b><small>{html.escape(ABOUT[k])}</small></span></a>'
        for k in ORDER for p in [catalog.PROFILES[k]])
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Learn Studios</title>
  <meta name="description" content="Short films for every concept in the NCERT textbooks, one studio per subject.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="static/app.css">
  <style>
    .hub {{ max-width: 760px; margin: 0 auto; padding: 40px 16px 48px; }}
    .hub h1 {{ font-size: clamp(30px, 6vw, 44px); margin-bottom: 10px; }}
    .hub p.sub {{ color: var(--muted); margin: 0 0 28px; }}
    .studios {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); }}
    .studio {{ display: flex; gap: 14px; align-items: center; padding: 16px; text-decoration: none;
              background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); }}
    .studio:hover {{ border-color: var(--accent); }}
    .studio b {{ display: block; font: 650 18px var(--serif); }}
    .studio small {{ color: var(--muted); font-size: 14px; }}
    .studio .mark {{ flex: none; }}
  </style>
</head>
<body>
  <main class="hub">
    <h1>Learn</h1>
    <p class="sub">Short films for every concept in the NCERT textbooks. Pick a studio; each asks for its own access code.</p>
    <nav class="studios">{cards}</nav>
  </main>
  <footer class="foot">Made from NCERT textbooks. Every film follows the book; anything added to explain it is checked against sources.</footer>
</body>
</html>'''


def build():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get('/', response_class=HTMLResponse)
    def index():
        return HTMLResponse(page(), headers={'Cache-Control': 'no-cache'})

    @app.get('/static/app.css')
    def css():
        return FileResponse(HERE / 'static' / 'app.css', headers={'Cache-Control': 'no-cache'})

    @app.get('/healthz')
    def healthz():
        return {'ok': True}

    @app.get('/{rest:path}')
    def unknown(rest: str):
        raise HTTPException(404)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=18600)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(build(), host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
