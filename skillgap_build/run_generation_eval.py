"""End-to-end RAG evaluation.

Step 1 (generate):  python run_generation_eval.py --split dev --prompts v1 v2
    -> results/generation_<split>.csv with automatic checks and empty `faithful` / `correct` columns.
Step 2 (annotate):  two team members fill `faithful` and `correct` with 1/0 independently
    (faithful = every claim is supported by the cited sources; correct = answers the question).
Step 3 (score):     python run_generation_eval.py --score results/generation_dev_annotated.csv
"""
import argparse,csv,json,sys
from collections import defaultdict
from pathlib import Path
from skillgap.core import load_documents,build_retriever,is_overview_question,role_overview
from skillgap.evaluation import load_questions
from skillgap.generation import answer_with_ollama,check_answer,PROMPTS

FIELDS=['id','split','role','question','expected_unanswerable','expected','retrieved','prompt','model','answer',
        'abstained','has_citation','citations_valid','invalid_citations','placeholder_count','grounding_pass','faithful','correct','annotator','notes']

def generate(a):
    docs=load_documents(a.documents); tests=[t for t in load_questions(a.questions) if t['split']==a.split]
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8'))
    retriever=build_retriever(docs,cfg['mode'],**cfg['params'])
    out=Path(a.output or f'results/generation_{a.split}.csv'); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,FIELDS); w.writeheader()
        for t in tests:
            # Same routing as app.py: role-level questions use the whole-role skill profile.
            overview=is_overview_question(t['question'])
            hits,extra=role_overview(docs,t.get('role'),cfg['k']) if overview else (retriever.search(t['question'],t.get('role'),cfg['k']),None)
            for prompt in a.prompts:
                try: answer=answer_with_ollama(t['question'],hits,model=a.model,role=t.get('role'),prompt=prompt,extra_sources=extra)
                except Exception as exc: sys.exit(f'Ollama call failed ({exc}). Start Ollama and pull {a.model} first.')
                c=check_answer(answer,hits,extra_ids=('SKILL_PROFILE',) if overview else ())
                w.writerow({'id':t['id'],'split':t['split'],'role':t.get('role'),'question':t['question'],
                    'expected_unanswerable':int(not t['relevant_doc_ids']),'expected':' '.join(t['relevant_doc_ids']),
                    'retrieved':' '.join(h.doc['doc_id'] for h in hits),'prompt':prompt,'model':a.model,'answer':answer,
                    'abstained':int(c['abstained']),'has_citation':int(c['has_citation']),'citations_valid':int(c['citations_valid']),
                    'invalid_citations':' '.join(c['invalid_citations']),'placeholder_count':int(c['placeholder_count']),
                    'grounding_pass':int(c['grounding_pass']),'faithful':'','correct':'','annotator':'','notes':''})
                print(t['id'],prompt,'abstained' if c['abstained'] else 'answered',flush=True)
    print('Wrote',out,'- now annotate faithful/correct (1/0) and run --score.')

def rate(rows,key):
    vals=[int(r[key]) for r in rows if str(r.get(key,'')).strip() in ('0','1')]
    return (sum(vals)/len(vals),len(vals)) if vals else (None,0)

def score(path):
    rows=list(csv.DictReader(open(path,encoding='utf-8'))); by=defaultdict(list)
    for r in rows: by[r['prompt']].append(r)
    fmt=lambda v:'--' if v[0] is None else f'{v[0]:.3f} (n={v[1]})'
    lines=[f'# Generation evaluation: {Path(path).name}','','| Prompt | Answer rate (answerable) | Correct abstention (unanswerable) | Citation present | Citations valid | Faithful | Correct |','|---|---|---|---|---|---|---|']
    summary={}
    for prompt,rs in sorted(by.items()):
        ans=[r for r in rs if r['expected_unanswerable']=='0']; una=[r for r in rs if r['expected_unanswerable']=='1']
        answered=[r for r in ans if r['abstained']=='0']
        s={'answer_rate':(1-rate(ans,'abstained')[0] if ans else None,len(ans)),'correct_abstention':rate(una,'abstained'),
           'citation_present':rate(answered,'has_citation'),'citations_valid':rate(answered,'citations_valid'),
           'faithful':rate(answered,'faithful'),'correct':rate(ans,'correct')}
        summary[prompt]=s
        lines.append(f'| {prompt} | '+' | '.join(fmt(s[k]) for k in s)+' |')
    lines+=['','Faithful/citation rates are over answered answerable questions; correct is over all answerable questions.',
            'Report inter-annotator agreement separately if two people annotated.']
    out=Path(path).with_suffix('.summary.md'); out.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines)); return summary

p=argparse.ArgumentParser()
p.add_argument('--documents',default='data/documents')
p.add_argument('--questions',default='data/evaluation/questions.json')
p.add_argument('--config',default='results/best_config.json')
p.add_argument('--split',default='dev',choices=['dev','test'])
p.add_argument('--prompts',nargs='+',default=['v1','v2'],choices=sorted(PROMPTS))
p.add_argument('--model',default='llama3.2:3b')
p.add_argument('--output')
p.add_argument('--score',help='annotated CSV to score')
a=p.parse_args()
score(a.score) if a.score else generate(a)
