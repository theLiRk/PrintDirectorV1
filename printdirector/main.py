import argparse,asyncio,logging,os,sys
import uvicorn
from .config import load_config,ConfigurationError
from .utils.logging import setup_logging
from .app import Runtime
from .overlay import create_app
async def serve(args):
 try: cfg=load_config(args.config)
 except ConfigurationError as e: print(f"PrintDirector configuration error: {e}",file=sys.stderr); return 2
 if not cfg.overlay.allow_lan and cfg.overlay.host not in {'127.0.0.1','localhost','::1'}:
   print("PrintDirector configuration error: overlay host must be localhost/127.0.0.1 unless allow_lan is enabled",file=sys.stderr); return 2
 setup_logging(cfg.logging.level)
 if not args.demo and not os.getenv(cfg.obs.password_env) and not cfg.obs.password:
  logging.warning("OBS password is not configured; OBS authentication may reject connections")
 logging.info("PrintDirector starting")
 rt=Runtime(cfg,args.demo); app=create_app(rt); server=uvicorn.Server(uvicorn.Config(app,host=cfg.overlay.host,port=cfg.overlay.port,log_level=cfg.logging.level.lower()))
 await rt.start()
 try: await server.serve()
 except asyncio.CancelledError:
  pass
 finally: await rt.stop()
 return 0
def main():
 p=argparse.ArgumentParser(); p.add_argument('--config',default='config.yaml'); p.add_argument('--demo',action='store_true'); a=p.parse_args(); raise SystemExit(asyncio.run(serve(a)))
if __name__=='__main__': main()
