"""Run the same contract task on an Apache-2.0 local model, with bounded retrieval."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import urllib.request

from .run import main as extract


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-path',required=True,type=Path)
    p.add_argument('--sources',required=True,type=Path)
    p.add_argument('--cache',required=True,type=Path)
    p.add_argument('--results',required=True,type=Path)
    p.add_argument('--papers',nargs='+',required=True)
    args=p.parse_args()
    executable=shutil.which('llama-server')
    if not executable: raise RuntimeError('Install llama.cpp with llama-server first')
    args.results.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    command=[executable,'-m',str(args.model_path),'-c','16384','-np','1','-b','128','-ub','64',
             '-ngl','99','--flash-attn','on','-ctk','q8_0','-ctv','q8_0','--port',str(port),
             '--chat-template-kwargs','{"enable_thinking":false}']
    started=time.monotonic()
    measurement={'peak_sampled_rss_bytes':0,'limit_exceeded':False,'sampling_seconds':.1}
    stopped=threading.Event()
    log=(args.results/'engine.log').open('w')
    process=subprocess.Popen(command,stdout=log,stderr=log)
    def monitor():
        while not stopped.is_set() and process.poll() is None:
            try:
                rss=int(subprocess.check_output(['ps','-o','rss=','-p',str(process.pid)],stderr=subprocess.DEVNULL).strip())*1024
                measurement['peak_sampled_rss_bytes']=max(measurement['peak_sampled_rss_bytes'],rss)
                # Leave headroom below the decimal 4 GB limit; sample throughout inference.
                if rss>3_700_000_000:
                    measurement['limit_exceeded']=True
                    process.kill()
                    return
            except (ValueError,subprocess.CalledProcessError):
                pass
            stopped.wait(.1)
    watcher=threading.Thread(target=monitor,daemon=True)
    watcher.start()
    try:
        base=f'http://127.0.0.1:{port}/v1'
        for _ in range(90):
            if process.poll() is not None: raise RuntimeError(f'llama-server exited {process.returncode}; see engine.log')
            try:
                with urllib.request.urlopen(base+'/models',timeout=1) as r:
                    if r.status==200:break
            except (OSError,ValueError):time.sleep(.5)
        else:raise RuntimeError('llama-server did not become ready within 45 seconds')
        for name in args.papers:
            if measurement['limit_exceeded']:raise RuntimeError('Local model reached the 3.7 GB stop threshold')
            extract(['--live','--model','Qwen3-0.6B-Q8_0','--base-url',base,'--sources',str(args.sources),
                     '--cache',str(args.cache),'--results',str(args.results),'--papers',name,
                     '--rounds','0','--max-tokens','2048','--timeout','180'])
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        stopped.set();watcher.join(timeout=2)
        log.close()
        (args.results/'runtime.json').write_text(json.dumps({'model':'Qwen3-0.6B-Q8_0',
            'license':'Apache-2.0',**measurement,'seconds':time.monotonic()-started,
            'server_exited':process.returncode is not None,'papers':args.papers},indent=2))


if __name__=='__main__':main()
