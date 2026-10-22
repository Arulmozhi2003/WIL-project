"""Build the labelled evaluation questions from the knowledge base (reproducible, seed 42).

Three question types, each with an explicit relevance rule:
  skill        "Is X asked for?" (paraphrased). Relevant = every document of the role whose skills include X.
  ad           "What does the <title> role at <company> involve?". Relevant = that ad (and reposts with the
               same title and company).
  unanswerable A question the documents cannot answer. The script checks with a regex that no document of
               the role mentions the topic; questions that fail the check are dropped, not relabelled.
Split: stratified by (role, type), 60% dev / 40% test.

Labels are rule-based. Before reporting, a team member should verify the sample in
data/evaluation/label_audit.csv and record the agreement rate.
"""
import csv,json,random,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from skillgap.core import load_documents

SKILL_QUESTIONS={
 'Graduate Data Analyst':[
  ('SQL','Do employers expect me to write database queries in SQL?'),
  ('Excel','How important are spreadsheet skills such as Microsoft Excel?'),
  ('Tableau','Is experience building dashboards in Tableau requested?'),
  ('Power BI','Do the ads mention Microsoft Power BI?'),
  ('Python','Is Python programming experience required for analyst roles?'),
  ('Statistics','Do these roles need a background in statistical analysis?'),
  ('ETL','Will I need to build ETL processes to load data?'),
  ('R','Is the R language asked for?')],
 'Graduate Data Scientist':[
  ('Python','Which data scientist roles ask for Python?'),
  ('R','Do data scientist ads want experience with R?'),
  ('Machine Learning','What machine learning experience do employers look for?'),
  ('Statistics','Is a strong statistics background expected?'),
  ('SQL','Do data scientists also need SQL for querying databases?'),
  ('Deep Learning','Do any roles want deep learning or neural network experience?'),
  ('SAS','Is SAS software mentioned as a requirement?'),
  ('Forecasting','Do the jobs involve forecasting or time series modelling?')],
 'Graduate Business/Data Analyst':[
  ('Excel','Do business analyst roles require advanced Excel?'),
  ('SQL','Is SQL knowledge expected for business analysts?'),
  ('Agile','Do these roles expect experience working in Agile or Scrum teams?'),
  ('Process Mapping','Is business process mapping part of the job?'),
  ('Power BI','Do business analyst ads mention Power BI reporting?'),
  ('Data Modelling','Do they ask for data modelling skills?'),
  ('Stakeholder Management','How much stakeholder engagement is involved in these roles?'),
  ('Data Visualisation','Will I be creating reports and dashboards?')],
}
UNANSWERABLE=[  # (question, regex that must NOT match any document of the role)
 ('What will the average salary for this role be in 2030?', r'2030'),
 ('Will the employer sponsor a 482 skilled worker visa?', r'\b482\b|sponsor'),
 ('Do these roles require knowledge of COBOL?', r'cobol'),
 ('Is a forklift licence required for this job?', r'forklift'),
 ('Will the company pay my university tuition fees?', r'tuition'),
 ('Do I need Kubernetes certification?', r'kubernetes'),
 ('What percentage of applicants pass the interview?', r'pass rate|percentage of applicants'),
 ('Can I work fully remotely from overseas?', r'overseas|offshore|anywhere in the world'),
]
AD_QUESTIONS_PER_ROLE=6; UNANSWERABLE_PER_ROLE=4; SEED=42

def main():
    rng=random.Random(SEED)
    docs=load_documents(ROOT/'data'/'documents')
    company=lambda d:d['text'].split(' at ',1)[1].split(' (',1)[0].strip()
    questions=[]; audit=[]
    for role in sorted(SKILL_QUESTIONS):
        role_docs=[d for d in docs if d['role']==role]
        for skill,q in SKILL_QUESTIONS[role]:
            rel=sorted(d['doc_id'] for d in role_docs if skill in d['skills'])
            if not rel: print('skip (no docs):',role,skill,file=sys.stderr); continue
            questions.append({'type':'skill','role':role,'question':q,'relevant_doc_ids':rel,'label_rule':f'documents of role whose skills include {skill}'})
        for d in rng.sample(role_docs,AD_QUESTIONS_PER_ROLE):
            rel=sorted(x['doc_id'] for x in role_docs if x['title'].lower()==d['title'].lower() and company(x).lower()==company(d).lower())
            questions.append({'type':'ad','role':role,'question':f"What does the {d['title']} role at {company(d)} involve?",
                              'relevant_doc_ids':rel,'label_rule':'the named advertisement'})
        kept=0
        for q,pattern in rng.sample(UNANSWERABLE,len(UNANSWERABLE)):
            if kept==UNANSWERABLE_PER_ROLE: break
            clash=[d['doc_id'] for d in role_docs if re.search(pattern,d['text'],re.I)]
            if clash: print(f'drop unanswerable for {role} ({len(clash)} docs mention it): {q}',file=sys.stderr); continue
            questions.append({'type':'unanswerable','role':role,'question':q,'relevant_doc_ids':[],'label_rule':f'no document of role matches /{pattern}/i'}); kept+=1
    # stratified split
    strata={}
    for q in questions: strata.setdefault((q['role'],q['type']),[]).append(q)
    for group in strata.values():
        rng.shuffle(group); n_dev=round(len(group)*0.6)
        for i,q in enumerate(group): q['split']='dev' if i<n_dev else 'test'
    for i,q in enumerate(questions,1): q['id']=f'Q{i:02d}'
    ordered=[{k:q[k] for k in ('id','split','type','role','question','relevant_doc_ids','label_rule')} for q in questions]
    out=ROOT/'data'/'evaluation'/'questions.json'
    out.write_text(json.dumps(ordered,indent=1,ensure_ascii=False),encoding='utf-8')
    # audit sample: up to 3 (question, relevant doc) pairs per skill question, with the evidence sentence
    by_id={d['doc_id']:d for d in docs}
    for q in ordered:
        if q['type']!='skill': continue
        skill=q['label_rule'].rsplit('include ',1)[1]
        for doc_id in rng.sample(q['relevant_doc_ids'],min(3,len(q['relevant_doc_ids']))):
            text=by_id[doc_id]['text']; sentences=re.split(r'(?<=[.!?•])\s+',text)
            from skillgap.core import extract_skills
            evidence=next((s for s in sentences if skill in extract_skills(s)),'')[:300]
            audit.append({'question_id':q['id'],'skill':skill,'doc_id':doc_id,'url':by_id[doc_id]['source_url'],'evidence':evidence,'correct (1/0)':''})
    with (ROOT/'data'/'evaluation'/'label_audit.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,list(audit[0])); w.writeheader(); w.writerows(audit)
    # skill-labelling sheet: 20 random documents for a person to label without looking at auto_skills first
    sheet=ROOT/'data'/'annotation'/'skill_labels.csv'; sheet.parent.mkdir(exist_ok=True)
    if not sheet.exists():
        with sheet.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,['doc_id','url','text','manual_skills','annotator','auto_skills'])
            w.writeheader()
            for d in rng.sample(docs,20):
                w.writerow({'doc_id':d['doc_id'],'url':d['source_url'],'text':d['text'],'manual_skills':'','annotator':'','auto_skills':'; '.join(d['skills'])})
    counts={}
    for q in ordered: counts[(q['split'],q['type'])]=counts.get((q['split'],q['type']),0)+1
    print(f'{len(ordered)} questions', dict(sorted(counts.items())), f'{len(audit)} audit rows',file=sys.stderr)

if __name__=='__main__':
    main()
