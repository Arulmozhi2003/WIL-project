"""Tune on dev questions, run the ablation ladder, then score every configuration once on test.

Outputs (results/): experiments.json, best_config.json, summary.md, tables.tex, failures_dev.md,
run_log.csv and figures/threshold_sweep.{pdf,png}. Selection never looks at test questions.
"""
import argparse,csv,hashlib,json,platform,sys
from datetime import datetime,timezone
from pathlib import Path
from skillgap.core import load_documents,build_retriever,BM25,DenseRetriever,role_skill_profile
from skillgap.evaluation import load_questions,evaluate,tune_bm25,tune_dense,bootstrap_ci,skill_extraction_eval,load_manual_skill_labels,choose_threshold,sweep_threshold

p=argparse.ArgumentParser()
p.add_argument('--documents',default='data/documents')
p.add_argument('--questions',default='data/evaluation/questions.json')
p.add_argument('--k',type=int,default=3)
p.add_argument('--out',default='results')
p.add_argument('--no-dense',action='store_true',help='skip dense and hybrid runs')
a=p.parse_args()
out=Path(a.out); (out/'figures').mkdir(parents=True,exist_ok=True)

docs=load_documents(a.documents); tests=load_questions(a.questions)
dev=[t for t in tests if t['split']=='dev']; test=[t for t in tests if t['split']=='test']
synthetic=any(d.get('source_type')=='SYNTHETIC_EXAMPLE' for d in docs)
if not dev: sys.exit('No dev questions: add "split": "dev" to at least some questions.')
if not test: print('WARNING: no test questions; held-out results will be missing.',file=sys.stderr)
fingerprint=hashlib.sha256((Path(a.questions).read_text(encoding='utf-8')+''.join(
    p.read_text(encoding='utf-8') for p in sorted(Path(a.documents).glob('*.json')))).encode()).hexdigest()[:12]

# --- tuning (dev only) ---
tuned=tune_bm25(docs,dev,a.k)
def with_threshold(params):
    """Tune only the abstention threshold for fixed BM25 settings (one controlled change)."""
    return {**params,'min_score':choose_threshold(sweep_threshold(BM25(docs,**params).score_all,dev,a.k))['threshold']}
starter=dict(stopwords=False,stemming=False,normalise=False,k1=1.5,b=0.75)
configs=[
 ('B0','BM25 starter baseline (k1=1.5, b=0.75, no threshold)','bm25',{**starter,'min_score':0.0}),
 ('B1','+ stopword removal','bm25',{**starter,'stopwords':True,'min_score':0.0}),
 ('B2','+ light stemming','bm25',{**starter,'stopwords':True,'stemming':True,'min_score':0.0}),
 ('B3','+ abstention threshold on raw score','bm25',with_threshold({**starter,'stopwords':True,'stemming':True})),
 ('B4','+ threshold on normalised score','bm25',with_threshold({**starter,'stopwords':True,'stemming':True,'normalise':True})),
 ('BT','BM25 fully tuned (grid: k1, b, stemming, normalisation, threshold)','bm25',tuned['best']),
]
dense_note=None; dense_tuned=None; encoder=None
if not a.no_dense:
    try:
        from sentence_transformers import SentenceTransformer
        encoder=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        dense=DenseRetriever(docs,encoder=encoder)
        dense_tuned=tune_dense(dense,dev,a.k)
        configs+=[('D0','Dense MiniLM, no threshold','dense',dict(min_score=0.0)),
                  ('D1','Dense MiniLM + tuned threshold','dense',dense_tuned['best']),
                  ('H1','Hybrid RRF (BT + D1)','hybrid',dict(bm25=tuned['best'],dense=dense_tuned['best']))]
    except ImportError as exc:
        dense_note=f'Dense/hybrid skipped: {exc}. Install requirements.txt to include them.'
        print('WARNING:',dense_note,file=sys.stderr)

runs=[]
for cid,label,mode,params in configs:
    r=build_retriever(docs,mode,encoder=encoder,**params)
    dev_res=evaluate(r.search,dev,a.k); test_res=evaluate(r.search,test,a.k) if test else None
    runs.append({'id':cid,'label':label,'mode':mode,'params':params,'dev':dev_res,'test':test_res})

# Final system = best dev selection score among the fully tuned systems; ties go to the simpler one.
finalists=[r for r in runs if r['id'] in ('BT','D1','H1')]
final=max(finalists,key=lambda r:r['dev']['summary']['selection_score'] or -1)
ci={m:bootstrap_ci(final['test']['per_question'],m) for m in ('selection_score','mean_ndcg_at_k','decision_accuracy')} if test else None

profiles={role:role_skill_profile(docs,role) for role in sorted({d['role'] for d in docs})}
extraction=skill_extraction_eval(docs,load_manual_skill_labels('data/annotation/skill_labels.csv'))
meta={'timestamp':datetime.now(timezone.utc).isoformat(timespec='seconds'),'python':platform.python_version(),
      'dataset_fingerprint':fingerprint,'synthetic_data_present':synthetic,'k':a.k,
      'documents':len(docs),'dev_questions':len(dev),'test_questions':len(test),
      'documents_per_role':{role:sum(d['role']==role for d in docs) for role in profiles},'dense_note':dense_note,
      'selection_rule':'max dev selection_score = mean(nDCG@k over answerable, decision accuracy over all); thresholds at the midpoint of the best dev plateau; ties -> simpler config'}
best={'mode':final['mode'],'params':final['params'],'k':a.k,'chosen_config':final['id'],'dataset_fingerprint':fingerprint}
(out/'best_config.json').write_text(json.dumps(best,indent=2),encoding='utf-8')
(out/'experiments.json').write_text(json.dumps({'meta':meta,'best':best,'runs':runs,'final_test_ci95':ci,
    'bm25_tuning':tuned,'dense_tuning':dense_tuned,'skill_profiles':profiles,'skill_extraction':extraction},indent=2,default=str),encoding='utf-8')

# --- run log: one line per invocation, the audit trail of iterations ---
log=out/'run_log.csv'; new=not log.exists()
with log.open('a',newline='',encoding='utf-8') as f:
    w=csv.writer(f)
    if new: w.writerow(['timestamp','dataset_fingerprint','documents','dev_q','test_q','chosen','params','dev_selection','test_selection','test_ndcg','test_decision_acc'])
    ts=final['test']['summary'] if test else {}
    w.writerow([meta['timestamp'],fingerprint,len(docs),len(dev),len(test),final['id'],json.dumps(final['params']),
                final['dev']['summary']['selection_score'],ts.get('selection_score'),ts.get('mean_ndcg_at_k'),ts.get('decision_accuracy')])

# --- human-readable outputs ---
fmt=lambda v:'--' if v is None else f'{v:.3f}'
cols=[('hit_rate_at_k','Hit@k'),('mrr','MRR'),('mean_ndcg_at_k','nDCG@k'),('decision_accuracy','Dec. acc.'),
      ('abstain_rate_unanswerable','Abstain (unans.)'),('false_abstain_rate_answerable','False abstain'),('selection_score','Selection')]
def md_table(split):
    lines=['| ID | Configuration | '+' | '.join(c[1] for c in cols)+' |','|'+'---|'*(len(cols)+2)]
    for r in runs:
        if r[split]: lines.append(f"| {r['id']} | {r['label']} | "+' | '.join(fmt(r[split]['summary'][c]) for c,_ in cols)+' |')
    return '\n'.join(lines)
def tex_escape(s): return s.replace('&',r'\&').replace('%',r'\%').replace('_',r'\_').replace('#',r'\#')
def tex_table(split,caption,label):
    head=' & '.join(['ID','Configuration']+[c[1] for c in cols])
    body='\n'.join(f"{r['id']} & {tex_escape(r['label'])} & "+' & '.join(fmt(r[split]['summary'][c]) for c,_ in cols)+r' \\'
                   for r in runs if r[split])
    n=len(dev) if split=='dev' else len(test)
    return (r'\begin{table}[ht]\centering\small'+'\n'+rf'\caption{{{caption} ($n={n}$ questions, $k={a.k}$).}}\label{{{label}}}'+'\n'
            +r'\resizebox{\linewidth}{!}{\begin{tabular}{ll'+'r'*len(cols)+'}\n\\toprule\n'+head+r' \\'+'\n\\midrule\n'+body+'\n\\bottomrule\n\\end{tabular}}\n\\end{table}\n')
tag=' (SYNTHETIC DATA -- NOT REPORTABLE)' if synthetic else ''
tex=[f'% Generated by run_experiments.py {meta["timestamp"]}, dataset {fingerprint}{tag}\n',
     tex_table('dev','Retrieval ablation on the development questions'+tag,'tab:ablation-dev')]
if test: tex.append(tex_table('test','Held-out test results for every configuration, selected on development only'+tag,'tab:ablation-test'))
role_rows='\n'.join(rf'{tex_escape(role)} & {meta["documents_per_role"][role]} & '+tex_escape(', '.join(f"{x['skill']} ({x['support_count']})" for x in prof[:8]))+r' \\' for role,prof in profiles.items())
tex.append(r'\begin{table}[ht]\centering\small'+'\n'+r'\caption{Knowledge base: documents per role and most frequently named skills (document counts)'+tag+r'.}\label{tab:kb}'
           +'\n'+r'\begin{tabular}{lrp{0.55\linewidth}}'+'\n\\toprule\nRole & Docs & Top skills (docs naming it) \\\\\n\\midrule\n'+role_rows+'\n\\bottomrule\n\\end{tabular}\n\\end{table}\n')
(out/'tables.tex').write_text('\n'.join(tex),encoding='utf-8')

md=[f'# SkillGap retrieval experiments{tag}','',f"Run {meta['timestamp']} · dataset `{fingerprint}` · {len(docs)} documents · {len(dev)} dev / {len(test)} test questions · k={a.k}",'',
    f"**Chosen system: {final['id']}** ({final['label']}) with `{json.dumps(final['params'])}`. {meta['selection_rule']}.",'']
if dense_note: md+=[f'> {dense_note}','']
md+=['## Development (used for tuning)','',md_table('dev'),'']
if test:
    md+=['## Held-out test (reported once, never tuned on)','',md_table('test'),'','95% bootstrap CIs for the chosen system on test:','']
    md+=[f'- {m}: {fmt(v[0])} – {fmt(v[1])}' if v else f'- {m}: n/a' for m,v in ci.items()]
    md.append('')
if extraction:
    md+=['## Skill extraction vs manual labels','',f"{extraction['documents']} documents · precision {fmt(extraction['precision'])} · recall {fmt(extraction['recall'])} · F1 {fmt(extraction['f1'])}",'']
(out/'summary.md').write_text('\n'.join(md),encoding='utf-8')

fails=[r for r in final['dev']['per_question'] if not r['decision_correct'] or r.get('hit_at_k') is False or (r.get('rr') or 1)<1]
fl=[f"# Dev failure cases for {final['id']}{tag}",'','Use these to motivate the next controlled change. Do not inspect test failures before the final run.','']
for r in fails:
    kind=('answered an unanswerable question' if r['expected_unanswerable'] and r['retrieved'] else 'abstained on an answerable question' if not r['retrieved']
          else 'relevant document missing from top-k' if r.get('hit_at_k') is False else 'relevant document ranked below 1')
    fl+=[f"- **{r['id']}** ({kind}): _{r['question']}_ · expected {r['expected'] or 'none'} · retrieved {r['retrieved'] or 'none'}"]
if not fails: fl.append('No failures on dev.')
(out/'failures_dev.md').write_text('\n'.join(fl)+'\n',encoding='utf-8')

try:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    b=tuned['best']; sweep=[t for t in tuned['trials'] if all(t[x]==b[x] for x in ('k1','b','stopwords','stemming','normalise'))]
    xs=[t['threshold'] for t in sweep]
    fig,ax=plt.subplots(figsize=(6,3.4))
    for key,name,color in (('mean_ndcg_at_k','nDCG@k (answerable)','#2a78d6'),('decision_accuracy','Answer/abstain accuracy','#eb6834')):
        ax.plot(xs,[t[key] if t[key] is not None else float('nan') for t in sweep],color=color,lw=2,marker='o',ms=5,drawstyle='steps-post',label=name)
    ax.axvspan(*tuned['best_plateau'],color='#f0efec',lw=0); ax.axvline(b['min_score'],color='#898781',lw=1,ls='--'); ax.text(b['min_score'],1.02,' chosen',color='#52514e',fontsize=8,va='bottom')
    ax.set_xlabel('BM25 abstention threshold'+(' (normalised score)' if b['normalise'] else ' (raw score)')); ax.set_ylabel('Score on dev'); ax.set_ylim(0,1.08)
    ax.set_title(f"BM25 threshold sweep (k1={b['k1']}, b={b['b']}){' — SYNTHETIC' if synthetic else ''}",fontsize=10,loc='left')
    for s in ('top','right'): ax.spines[s].set_visible(False)
    ax.grid(axis='y',color='#e5e4e0',lw=0.6); ax.legend(frameon=False,fontsize=8,loc='lower left')
    fig.tight_layout(); fig.savefig(out/'figures'/'threshold_sweep.pdf'); fig.savefig(out/'figures'/'threshold_sweep.png',dpi=200)
except ImportError:
    print('matplotlib not installed; figure skipped.',file=sys.stderr)

print((out/'summary.md').read_text(encoding='utf-8'))
