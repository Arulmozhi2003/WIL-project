import argparse,json
from pathlib import Path
from skillgap.evaluation import run_retrieval_eval
p=argparse.ArgumentParser(description='Evaluate one retrieval configuration. Use run_experiments.py for tuning.')
p.add_argument('--documents',default='data/documents')
p.add_argument('--questions',default='data/evaluation/questions.json')
p.add_argument('--method',choices=['bm25','dense','hybrid'],default='bm25')
p.add_argument('--config',help='results/best_config.json from run_experiments.py (overrides --method/--k)')
p.add_argument('--k',type=int,default=3)
p.add_argument('--output',default='results/retrieval_eval.json')
a=p.parse_args()
mode,k,params=a.method,a.k,{}
if a.config:
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8')); mode,k,params=cfg['mode'],cfg['k'],cfg['params']
result=run_retrieval_eval(a.documents,a.questions,mode,k,**params)
Path(a.output).parent.mkdir(parents=True,exist_ok=True)
Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result['summary'],indent=2))
