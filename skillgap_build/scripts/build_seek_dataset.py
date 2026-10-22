"""Build the SkillGap knowledge base from the public SEEK Australia dataset (reproducible).

Source: JobsPikr (2018). "30000 job postings from SEEK Australia". Zenodo. https://doi.org/10.5281/zenodo.1220874
Licence: CC BY 4.0. Postings dated 10-17 April 2018.

Steps: download (if missing) -> verify MD5 against Zenodo -> select the three role families by job title
(documented rules below) -> drop senior roles -> write data/raw/seek_selected.csv -> run ingest.py.

Usage:  python scripts/build_seek_dataset.py [--keep-existing]
"""
import argparse,csv,hashlib,re,subprocess,sys,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data'/'raw'/'seek_australia.csv'
URL='https://zenodo.org/api/records/1220874/files/seek_australia.csv/content'
MD5='7d8136907b7f4d4aa9958ea676aa6247'
sys.path.insert(0,str(ROOT))
from skillgap.core import extract_skills

# Selection rules (applied to the job title, case-insensitive). Kept deliberately explicit for the report.
ROLE_RULES=[
 ('Graduate Data Scientist', r'data scien|machine learning|\bstatistician\b|quantitative analyst',
                             r'developer|full ?stack|front ?end'),
 ('Graduate Data Analyst',   r'\b(data|reporting|insights?|bi|business intelligence|analytics)\b.*\banalyst\b|\bdata analytics\b',
                             r'business analyst'),
 ('Graduate Business/Data Analyst', r'business (systems |data |process )?analyst', None),
]
SENIOR=r'\b(senior|snr|sr\.?|lead|principal|manager|head|director|chief|architect|consultant|specialist|executive)\b'
# A Business/Data Analyst ad must name at least one data skill, otherwise it is a generic BA role.
DATA_SKILLS={'SQL','Python','R','Excel','Power BI','Tableau','SAS','Data Modelling','Data Visualisation','Data Warehousing',
             'ETL','Statistics','Data Cleaning','Qlik','Looker','Pandas','Machine Learning'}

def download():
    RAW.parent.mkdir(parents=True,exist_ok=True)
    if not RAW.exists():
        print('Downloading',URL,file=sys.stderr); urllib.request.urlretrieve(URL,RAW)
    digest=hashlib.md5(RAW.read_bytes()).hexdigest()
    if digest!=MD5: sys.exit(f'Checksum mismatch: {digest} != {MD5}')

def assign_role(title:str,text:str):
    if re.search(SENIOR,title,re.I): return None,'senior title'
    for role,include,exclude in ROLE_RULES:
        if re.search(include,title,re.I):
            if exclude and re.search(exclude,title,re.I): continue
            if role=='Graduate Business/Data Analyst' and not DATA_SKILLS & set(extract_skills(text)):
                return None,'business analyst ad names no data skill'
            return role,None
    return None,'title not in scope'

def main():
    p=argparse.ArgumentParser(); p.add_argument('--keep-existing',action='store_true',help='do not delete current documents first')
    a=p.parse_args()
    download()
    rows=list(csv.DictReader(RAW.open(encoding='utf-8-sig')))
    selected=[]; reasons={}
    for r in rows:
        role,why=assign_role(r['job_title'],r['job_description'] or '')
        if role:
            seek_id=r['url'].rstrip('/').rsplit('/',1)[-1]
            selected.append({'seek_id':seek_id,'role':role,'job_title':r['job_title'].strip(),
                'text':f"{r['job_title'].strip()} at {r['company_name'].strip()} ({r['city']}, {r['state']}; {r['job_type']}; salary: {r['salary_offered'] or 'not stated'}). {r['job_description']}",
                'url':r['url'],'post_date':r['post_date'][:10],'company':r['company_name'],'category':r['category']})
        else: reasons[why]=reasons.get(why,0)+1
    out=ROOT/'data'/'raw'/'seek_selected.csv'
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,list(selected[0])); w.writeheader(); w.writerows(selected)
    counts={}
    for s in selected: counts[s['role']]=counts.get(s['role'],0)+1
    print(f'{len(rows)} postings -> {len(selected)} selected {counts}; excluded {reasons}',file=sys.stderr)
    docs=ROOT/'data'/'documents'
    if not a.keep_existing:
        prov=ROOT/'data'/'provenance'
        for f in list(docs.glob('*.json'))+[prov/'MANIFEST.csv',prov/'NEAR_DUPLICATES.csv']:
            if f.exists(): f.unlink()
    subprocess.run([sys.executable,str(ROOT/'ingest.py'),str(out),'--out',str(docs),'--provenance',str(ROOT/'data'/'provenance'),'--text-col','text','--title-col','job_title',
                    '--url-col','url','--date-col','post_date','--role-col','role','--id-col','seek_id',
                    '--source-type','PUBLIC_JOB_AD_SEEK_2018_CC_BY_4.0','--min-chars',str(300)],check=True,cwd=ROOT)

if __name__=='__main__':
    main()
