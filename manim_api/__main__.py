import argparse
import uvicorn
from .app import create_app


def main():
    parser=argparse.ArgumentParser(description='Qwen research, Manim code generation and silent MP4 API')
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--port',type=int,default=18610)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be between 1 and 65535')
    app=create_app()
    print(f'API token file: {app.state.store.root / "api-token"} (or set MANIM_API_KEY)',flush=True)
    uvicorn.run(app,host=args.host,port=args.port,log_level='info')


if __name__=='__main__':main()
