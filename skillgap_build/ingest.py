"""Convert a raw collection of job ads (CSV / JSON / JSONL) into data/documents/*.json.

Example:
  python ingest.py raw/ads.csv --text-col description --title-col job_title --url-col link \
      --date-col date_collected --role-col role --source-type PUBLIC_JOB_AD

Skills are taken from --skills-col when given (skills_source='manual'); otherwise they are extracted by
exact taxonomy match (skills_source='auto_taxonomy'). Exact duplicates (same normalised text) are dropped.
Provenance (MANIFEST.csv, NEAR_DUPLICATES.csv) is written to --provenance (default data/provenance).
"""
import argparse,csv,hashlib,json,re,sys
from pathlib import Path
from skillgap.core import extract_skills,normalise_skill

ROLE_PREFIX={'Graduate Data Analyst':'DA','Graduate Data Scientist':'DS','Graduate Business/Data Analyst':'BA'}

def read_rows(path:Path)->list[dict]:
    if path.suffix.lower()=='.csv':
        return list(csv.DictReader(path.open(encoding='utf-8-sig')))
    if path.suffix.lower()=='.jsonl':
        return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
    data=json.loads(path.read_text(encoding='utf-8'))
    return data if isinstance(data,list) else data.get('records') or data.get('data') or [data]

def clean(text:str)->str:
    text=str(text or '') if str(text or '')!='nan' else ''
    if any(m in text for m in ('â€','Ã','Â')):               # UTF-8 read as cp1252 ("â€“" -> "–")
        try: text=text.encode('cp1252').decode('utf-8')
        except UnicodeError:
            for bad,good in (('â€“','–'),('â€”','—'),('â€™',"'"),('â€˜',"'"),('â€œ','"'),('â€\x9d','"'),('â€¢','•'),('â€¦','…'),('Â',' ')):
                text=text.replace(bad,good)
    text=re.sub(r'<[^>]+>',' ',text)                          # strip HTML tags
    text=re.sub(r'&nbsp;|&amp;',lambda m:' ' if m.group()=='&nbsp;' else '&',text)
    return re.sub(r'\s+',' ',text).strip()

p=argparse.ArgumentParser()
p.add_argument('inputs',nargs='+')
p.add_argument('--out',default='data/documents')
p.add_argument('--provenance',default='data/provenance')
p.add_argument('--text-col',default='text'); p.add_argument('--title-col',default='title')
p.add_argument('--url-col',default='source_url'); p.add_argument('--date-col',default='collected_date')
p.add_argument('--role-col',default='role'); p.add_argument('--role',help='fixed role for every row')
p.add_argument('--skills-col',help='column with manually annotated skills (list or ; / , separated)')
p.add_argument('--id-col',help='stable source id column, otherwise ids are assigned')
p.add_argument('--source-type',default='PUBLIC_JOB_AD')
p.add_argument('--min-chars',type=int,default=200,help='drop rows whose text is shorter (likely truncated)')
p.add_argument('--remove-synthetic',action='store_true',help='delete SYNTHETIC_*.json from the output folder')
a=p.parse_args()

out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
prov=Path(a.provenance); prov.mkdir(parents=True,exist_ok=True)
if a.remove_synthetic:
    for f in out.glob('SYNTHETIC_*.json'): f.unlink()
seen={hashlib.sha1(clean(json.loads(f.read_text())['text']).lower().encode()).hexdigest() for f in out.glob('*.json')}
counters={}; manifest=[]; dropped={'duplicate':0,'near_duplicate':0,'too_short':0,'missing_field':0}
shingles_by_title={}; near_dups=[]
def shingles(text,n=5):
    words=re.findall(r'[a-z0-9]+',text.lower()); return {' '.join(words[i:i+n]) for i in range(max(len(words)-n+1,1))}
for src in map(Path,a.inputs):
    for i,row in enumerate(read_rows(src)):
        text=clean(row.get(a.text_col)); role=a.role or str(row.get(a.role_col,'')).strip()
        title=clean(row.get(a.title_col)); url=str(row.get(a.url_col,'')).strip(); date=str(row.get(a.date_col,'')).strip()
        if not all((text,role,title,url,date)): dropped['missing_field']+=1; continue
        if len(text)<a.min_chars: dropped['too_short']+=1; continue
        h=hashlib.sha1(text.lower().encode()).hexdigest()
        if h in seen: dropped['duplicate']+=1; continue
        seen.add(h)
        # Reposts of the same ad (e.g. one per city) share a title and >= 80% of their 5-word shingles.
        sh=shingles(text); title_key=re.sub(r'[^a-z0-9]+',' ',title.lower()).strip()
        twin=next((d for d,o in shingles_by_title.get(title_key,[]) if len(sh&o)/len(sh|o)>=0.8),None)
        if twin: dropped['near_duplicate']+=1; near_dups.append({'kept':twin,'dropped_url':url,'title':title}); continue
        prefix=ROLE_PREFIX.get(role,re.sub(r'[^A-Z]','',role.title())[:3] or 'DOC')
        if a.id_col and str(row.get(a.id_col,'')).strip():
            doc_id=f"{prefix}_{re.sub(r'[^A-Za-z0-9]+','-',str(row[a.id_col]).strip())}"
        else:
            counters[prefix]=counters.get(prefix,len(list(out.glob(f'{prefix}*.json'))))+1; doc_id=f'{prefix}{counters[prefix]:03d}'
        if a.skills_col and row.get(a.skills_col):
            raw=row[a.skills_col]; raw=raw if isinstance(raw,list) else re.split(r'[;,|]',str(raw))
            skills=sorted({normalise_skill(s) for s in raw if s.strip()}); how='manual'
        else:
            skills=extract_skills(text); how='auto_taxonomy'
        doc={'doc_id':doc_id,'role':role,'title':title,'text':text,'skills':skills,'skills_source':how,
             'source_url':url,'source_type':a.source_type,'collected_date':date,'raw_file':src.name,'raw_row':i}
        shingles_by_title.setdefault(title_key,[]).append((doc_id,sh))
        (out/f'{doc_id}.json').write_text(json.dumps(doc,indent=2,ensure_ascii=False),encoding='utf-8')
        manifest.append({k:doc[k] for k in ('doc_id','role','title','source_url','collected_date','source_type','skills_source','raw_file','raw_row')}|{'n_skills':len(skills),'chars':len(text)})

mpath=prov/'MANIFEST.csv'; new=not mpath.exists()
if manifest:
    with mpath.open('a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,list(manifest[0])); new and w.writeheader(); w.writerows(manifest)
if near_dups:
    with (prov/'NEAR_DUPLICATES.csv').open('a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,list(near_dups[0])); w.writeheader(); w.writerows(near_dups)
print(f'Imported {len(manifest)} documents; dropped {dropped}.',file=sys.stderr)
