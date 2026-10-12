import argparse

import uvicorn

from .app import create_app

parser = argparse.ArgumentParser(description='Lesson Studio')
parser.add_argument('--host', default='0.0.0.0')
parser.add_argument('--port', type=int, default=18610)
args = parser.parse_args()
uvicorn.run(create_app(), host=args.host, port=args.port)
