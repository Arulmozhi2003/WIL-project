from __future__ import annotations
import itertools,json,math,random
from pathlib import Path
from typing import Any,Callable
from .core import load_documents,build_retriever,extract_skills,BM25,DenseRetriever,HybridRetriever,Hit

SearchFn=Callable[[str,'str|None',int],list[Hit]]
METRICS=('hit_rate_at_k','mrr','mean_ndcg_at_k','recall_at_k','decision_accuracy','abstain_rate_unanswerable','false_abstain_rate_answerable','selection_score')

def load_questions(path)->list[dict[str,Any]]:
    tests=json.loads(Path(path).read_text(encoding='utf-8'))
    ids=[t['id'] for t in tests]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate question id')
    for t in tests: t.setdefault('split','dev')
    return tests

def score_question(test,got:list[str],k:int)->dict[str,Any]:
    relevant=set(test['relevant_doc_ids']); answerable=bool(relevant)
    row={'id':test['id'],'question':test['question'],'role':test.get('role'),'split':test['split'],
         'expected':sorted(relevant),'retrieved':got,'expected_unanswerable':not answerable,
         'retrieval_unanswered':not got,'decision_correct':bool(got)==answerable}
    if answerable:
        row['hit_at_k']=any(d in relevant for d in got)
        row['rr']=next((1/(i+1) for i,d in enumerate(got) if d in relevant),0.0)
        dcg=sum(1/math.log2(i+2) for i,d in enumerate(got) if d in relevant)
        row['ndcg_at_k']=dcg/sum(1/math.log2(i+2) for i in range(min(len(relevant),k)))
        row['recall_at_k']=len(relevant.intersection(got))/len(relevant)
    return row

def _mean(values):
    values=[float(v) for v in values if v is not None]
    return sum(values)/len(values) if values else None

def summarise(rows:list[dict[str,Any]])->dict[str,Any]:
    ans=[r for r in rows if not r['expected_unanswerable']]; una=[r for r in rows if r['expected_unanswerable']]
    s={'question_count':len(rows),'answerable_count':len(ans),'unanswerable_count':len(una),
       'hit_rate_at_k':_mean(r['hit_at_k'] for r in ans),'mrr':_mean(r['rr'] for r in ans),
       'mean_ndcg_at_k':_mean(r['ndcg_at_k'] for r in ans),'recall_at_k':_mean(r['recall_at_k'] for r in ans),
       'decision_accuracy':_mean(r['decision_correct'] for r in rows),
       'abstain_rate_unanswerable':_mean(r['retrieval_unanswered'] for r in una),
       'false_abstain_rate_answerable':_mean(r['retrieval_unanswered'] for r in ans)}
    # Model-selection objective: ranking quality and the answer/abstain decision weighted equally.
    parts=[v for v in (s['mean_ndcg_at_k'],s['decision_accuracy']) if v is not None]
    s['selection_score']=sum(parts)/len(parts) if parts else None
    return s

def evaluate(search:SearchFn,tests,k:int)->dict[str,Any]:
    rows=[score_question(t,[h.doc['doc_id'] for h in search(t['question'],t.get('role'),k)],k) for t in tests]
    return {'summary':summarise(rows),'per_question':rows}

def bootstrap_ci(rows,metric='selection_score',n=2000,seed=0,alpha=0.05):
    """Percentile bootstrap over questions; wide intervals are expected on a small test set."""
    if not rows: return None
    rng=random.Random(seed); values=[]
    for _ in range(n):
        v=summarise([rng.choice(rows) for _ in rows])[metric]
        if v is not None: values.append(v)
    if not values: return None
    values.sort()
    return (values[int(alpha/2*len(values))],values[min(len(values)-1,int((1-alpha/2)*len(values)))])

def _threshold_candidates(scores:list[float])->list[float]:
    """0 plus midpoints between consecutive observed top scores, so every distinct cut is tried once."""
    uniq=sorted(set(round(s,6) for s in scores))
    return [0.0]+[(a+b)/2 for a,b in zip(uniq,uniq[1:])]+([uniq[-1]+1e-6] if uniq else [])

def _thresholded(ranker:Callable[[str,'str|None'],list[Hit]],cache:dict,threshold:float)->SearchFn:
    def search(q,role,k):
        key=(q,role)
        if key not in cache: cache[key]=ranker(q,role)
        return [h for h in cache[key] if h.score>=threshold][:k]
    return search

def sweep_threshold(ranker,tests,k)->list[dict[str,Any]]:
    cache={}
    tops=[]
    for t in tests:
        key=(t['question'],t.get('role'))
        if key not in cache: cache[key]=ranker(*key)
        tops.extend(h.score for h in cache[key][:k])
    return [{'threshold':th,**evaluate(_thresholded(ranker,cache,th),tests,k)['summary']} for th in _threshold_candidates(tops)]

def choose_threshold(sweep:list[dict[str,Any]])->dict[str,Any]:
    """Among thresholds with the best dev selection score, take the middle of the longest contiguous run.

    Picking the edge of the optimal range (the first run of this code did) overfits: a test question
    scoring just under a dev question is then rejected. The middle maximises the margin on both sides.
    """
    best=max((r['selection_score'] or -1) for r in sweep)
    runs,cur=[],[]
    for r in sorted(sweep,key=lambda r:r['threshold']):
        if (r['selection_score'] or -1)==best: cur.append(r)
        elif cur: runs.append(cur); cur=[]
    if cur: runs.append(cur)
    run=max(runs,key=len)
    return {'threshold':(run[0]['threshold']+run[-1]['threshold'])/2,'selection_score':best,'plateau':[run[0]['threshold'],run[-1]['threshold']]}

DEFAULT_BM25={'k1':1.5,'b':0.75}

def tune_bm25(docs,dev,k,grid=None)->dict[str,Any]:
    grid=grid or {'k1':[0.9,1.2,1.5,2.0],'b':[0.3,0.5,0.75,0.9],'stopwords':[True],'stemming':[False,True],'normalise':[False,True]}
    trials=[]; configs=[]
    for k1,b,sw,st,nm in itertools.product(grid['k1'],grid['b'],grid['stopwords'],grid['stemming'],grid['normalise']):
        bm=BM25(docs,k1=k1,b=b,stopwords=sw,stemming=st,normalise=nm)
        sweep=sweep_threshold(bm.score_all,dev,k)
        params={'k1':k1,'b':b,'stopwords':sw,'stemming':st,'normalise':nm}
        trials+=[{**params,**row} for row in sweep]
        choice=choose_threshold(sweep)
        configs.append({'params':{**params,'min_score':choice['threshold']},'selection_score':choice['selection_score'],'plateau':choice['plateau']})
    # Ties (common on a small dev set): prefer normalised scores, whose threshold transfers across questions;
    # then the widest optimal threshold range (largest safety margin); then settings nearest the defaults.
    key=lambda c:(c['selection_score'],c['params']['normalise'],
                  round(c['plateau'][1]-c['plateau'][0],6) if c['params']['normalise'] else 0,
                  -abs(c['params']['k1']-DEFAULT_BM25['k1'])-abs(c['params']['b']-DEFAULT_BM25['b']))
    best=max(configs,key=key)
    return {'best':best['params'],'best_plateau':best['plateau'],'configs':configs,'trials':trials}

def tune_dense(dense:DenseRetriever,dev,k)->dict[str,Any]:
    trials=sweep_threshold(dense.score_all,dev,k); choice=choose_threshold(trials)
    return {'best':{'min_score':choice['threshold']},'best_plateau':choice['plateau'],'trials':trials}

def load_manual_skill_labels(path)->dict[str,set[str]]:
    """doc_id -> skills from a filled-in data/annotation/skill_labels.csv (rows with empty manual_skills are skipped)."""
    import csv
    from .core import normalise_skill
    if not Path(path).exists(): return {}
    rows=csv.DictReader(open(path,encoding='utf-8'))
    return {r['doc_id']:{normalise_skill(s) for s in r['manual_skills'].split(';') if s.strip() and s.strip()!='NONE'}
            for r in rows if r.get('manual_skills','').strip()}

def skill_extraction_eval(docs,manual:dict[str,set[str]]|None=None)->dict[str,Any]|None:
    """Micro P/R/F1 of the taxonomy extractor against skills a person annotated
    (documents with skills_source == 'manual', or doc_id -> skills from load_manual_skill_labels)."""
    manual=manual or {}
    gold=[{**d,'skills':sorted(manual[d['doc_id']])} if d['doc_id'] in manual else d for d in docs
          if d['doc_id'] in manual or d.get('skills_source')=='manual']
    if not gold: return None
    tp=fp=fn=0; errors=[]
    for d in gold:
        pred=set(extract_skills(d['text'])); true=set(d['skills'])
        tp+=len(pred&true); fp+=len(pred-true); fn+=len(true-pred)
        if pred!=true: errors.append({'doc_id':d['doc_id'],'false_positive':sorted(pred-true),'missed':sorted(true-pred)})
    p=tp/(tp+fp) if tp+fp else 0.0; r=tp/(tp+fn) if tp+fn else 0.0
    return {'documents':len(gold),'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.0,'errors':errors}

def run_retrieval_eval(doc_folder,questions_path,mode='bm25',k=3,**params):
    """Single-configuration evaluation (kept for run_eval.py)."""
    docs=load_documents(doc_folder); tests=load_questions(questions_path)
    retriever=build_retriever(docs,mode,**params)
    result=evaluate(retriever.search,tests,k)
    result['summary']={'mode':mode,'k':k,'params':{p:v for p,v in params.items() if p!='encoder'},'document_count':len(docs),**result['summary'],
        'note':'Retrieval metrics only. LLM correctness, faithfulness and citation accuracy are measured by run_generation_eval.py plus human annotation.'}
    return result
