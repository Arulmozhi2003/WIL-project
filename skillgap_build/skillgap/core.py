from __future__ import annotations
import json, math, re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Keeps C++, C#, Node.js as single tokens; a trailing sentence full stop is not part of a token.
TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*[+#]*", re.I)

# Function words only. Domain words such as "job", "role" or "skills" are deliberately kept:
# BM25's IDF already down-weights them, and removing them would empty generic questions.
STOPWORDS = frozenset("""
a about above after again all am an and any are as at be been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers
him his how i if in into is it its itself just me more most my no nor not now of off on once only or
other our ours out over own same she should so some such than that the their theirs them then there
these they this those through to too under until up very was we were what when where which while who
whom why will with would you your yours
""".split())

# canonical skill -> surface forms. Forms are matched on word boundaries; forms in CASE_SENSITIVE are
# matched exactly because their lowercase spelling is an ordinary word ("r", "excel", "spark").
SKILL_TAXONOMY: dict[str, list[str]] = {
    "SQL": ["sql", "structured query language", "t-sql", "tsql", "pl/sql", "mysql", "postgresql", "postgres"],
    "Python": ["python"],
    "R": ["R", "r programming", "rstudio"],
    "Excel": ["Excel", "ms excel", "microsoft excel", "advanced excel", "spreadsheets"],
    "Power BI": ["power bi", "powerbi", "microsoft power bi"],
    "Tableau": ["tableau"],
    "Looker": ["looker", "looker studio"],
    "Qlik": ["qlik", "qlikview", "qlik sense"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Spark": ["Spark", "apache spark", "pyspark"],
    "Hadoop": ["hadoop"],
    "Databricks": ["databricks"],
    "Snowflake": ["Snowflake"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform", "bigquery"],
    "Git": ["git", "github", "gitlab", "version control"],
    "SAS": ["SAS"],
    "SPSS": ["spss"],
    "Java": ["java"],
    "Scala": ["scala"],
    "C++": ["c++"],
    "ETL": ["etl", "elt", "data pipelines", "data pipeline"],
    "Data Warehousing": ["data warehouse", "data warehousing"],
    "Data Modelling": ["data modelling", "data modeling"],
    "Data Visualisation": ["data visualisation", "data visualization", "dashboards", "dashboarding", "dashboard"],
    "Data Cleaning": ["data cleaning", "data cleansing", "data wrangling", "data preparation"],
    "Statistics": ["statistics", "statistical analysis", "statistical modelling", "statistical modeling", "stats"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "neural networks", "neural network"],
    "NLP": ["nlp", "natural language processing"],
    "A/B Testing": ["a/b testing", "ab testing", "experimentation", "experimental design"],
    "Forecasting": ["forecasting", "time series"],
    "Business Analysis": ["business analysis", "requirements gathering", "requirements elicitation"],
    "Process Mapping": ["process mapping", "process modelling", "bpmn"],
    "Agile": ["agile", "scrum"],
    "Jira": ["jira"],
    "Communication": ["communication", "communication skills", "stakeholder communication", "written communication", "verbal communication"],
    "Stakeholder Management": ["stakeholder management", "stakeholder engagement"],
    "Problem Solving": ["problem solving", "problem-solving", "analytical thinking", "critical thinking"],
    "Teamwork": ["teamwork", "collaboration", "team player"],
    "Attention to Detail": ["attention to detail"],
    "Presentation": ["presentation skills", "presenting", "storytelling", "data storytelling"],
}
CASE_SENSITIVE = {"R", "Excel", "Spark", "Snowflake", "SAS"}

def _alias_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", text.strip().lower())).strip(" .,;:")

SKILL_ALIASES = {_alias_key(form): canon for canon, forms in SKILL_TAXONOMY.items() for form in forms + [canon]}

def stem(token: str) -> str:
    """Light suffix stripper so requested/requests/requires/requirement(s) share a stem."""
    if not token.isalpha() or len(token) <= 3: return token
    if token.endswith("ies") and len(token) > 4: token = token[:-3] + "y"
    elif token.endswith(("sses", "xes", "ches", "shes")): token = token[:-2]
    elif token.endswith(("ing", "ed")) and len(token) > 5:
        token = token[:-3] if token.endswith("ing") else token[:-2]
        if token[-1] == token[-2] and token[-1] not in "sz": token = token[:-1]  # modelling -> model
    elif token.endswith("s") and not token.endswith(("ss", "is", "us")): token = token[:-1]
    return token[:-1] if token.endswith("e") and len(token) > 4 else token

def tokenize(text: str, stopwords: bool = False, stemming: bool = False) -> list[str]:
    tokens = TOKEN.findall(text.lower())
    if stopwords: tokens = [t for t in tokens if t not in STOPWORDS]
    return [stem(t) for t in tokens] if stemming else tokens

def normalise_skill(text: str) -> str:
    return SKILL_ALIASES.get(_alias_key(text), text.strip())

def _form_pattern(form: str) -> re.Pattern:
    body = r"[\s_-]+".join(re.escape(part) for part in re.split(r"[\s_-]+", form))  # "Power-BI" == "power bi"
    return re.compile(r"(?<![A-Za-z0-9&])" + body + r"(?![A-Za-z0-9+#&])", 0 if form in CASE_SENSITIVE else re.I)

_EXTRACTORS = [(canon, _form_pattern(form)) for canon, forms in SKILL_TAXONOMY.items() for form in forms]

def extract_skills(text: str) -> list[str]:
    """Skills explicitly named in the text (taxonomy match only, no inference)."""
    return sorted({canon for canon, pattern in _EXTRACTORS if pattern.search(text)})

# Experience level, from explicit wording only. Numerical requirements take precedence over
# title wording. We intentionally keep "experience not stated" separate from zero experience.
# The parser uses the *maximum* value in a range (e.g. 1–2 -> 2; 1–4 -> 4), because a
# candidate may be expected to satisfy the upper end and the ad is not a strict 0–1 year ad.
_RANGE = r"(?P<lo>\d{1,2})\s*(?P<plus>\+)?(?:\s*(?:-|–|—|to)\s*(?P<hi>\d{1,2})\s*\+?)?\s*(?:years?|yrs?)\+?"
_YEARS_BEFORE_EXPERIENCE = re.compile(
    _RANGE + r"(?:'|’)?\s*(?:of\s+)?(?:[\w/&,-]+\s+){0,7}?(?:experience|working\s+(?:with|in|as))", re.I
)
_EXPERIENCE_BEFORE_YEARS = re.compile(
    r"(?:experience|working\s+(?:with|in|as))[^.;\n]{0,80}?" + _RANGE, re.I
)
_ENTRY_TITLE = re.compile(r'\b(graduate|junior|entry[- ]level|trainee|cadet|intern(?:ship)?)\b', re.I)
LEVELS = ('Graduate/entry wording', '0–1 year', 'Experience not stated', '2+ years')
EARLY_CAREER = ('Graduate/entry wording', '0–1 year')

def _experience_year_requirements(text: str) -> list[int]:
    """Return explicit experience-year requirements found in an ad.

    Only patterns tied to the word 'experience' or 'working with/in/as' are counted, which avoids
    company ages and contract lengths. For ranges the upper bound is returned.
    """
    values=[]
    for pattern in (_YEARS_BEFORE_EXPERIENCE, _EXPERIENCE_BEFORE_YEARS):
        for m in pattern.finditer(text):
            lo=int(m.group('lo')); hi=m.group('hi')
            value=int(hi) if hi is not None else lo
            if 0 <= value <= 15:
                values.append(value)
    return values

def experience_level(doc: dict[str, Any]) -> str:
    """Classify an ad from explicit evidence only.

    Explicit numerical experience requirements in the description override title wording.
    A graduate/junior/entry title without a numerical conflict is only title-based evidence; it is
    not treated as proof that the role requires zero prior experience.
    """
    years=_experience_year_requirements(doc['text'])
    if years:
        return '0–1 year' if max(years) <= 1 else '2+ years'
    if _ENTRY_TITLE.search(doc['title']):
        return 'Graduate/entry wording'
    return 'Experience not stated'

def load_documents(folder: str | Path) -> list[dict[str, Any]]:
    docs=[]
    for path in sorted(Path(folder).glob('*.json')):
        item=json.loads(path.read_text(encoding='utf-8'))
        required=('doc_id','role','title','text','source_url','source_type','collected_date')
        if any(not str(item.get(k,'')).strip() for k in required):
            raise ValueError(f'{path.name}: missing required document fields')
        if item['doc_id'] in {d['doc_id'] for d in docs}:
            raise ValueError(f'duplicate doc_id: {item["doc_id"]}')
        skills=item.get('skills',[])
        if not isinstance(skills,list) or not all(isinstance(s,str) for s in skills):
            raise ValueError(f'{path.name}: "skills" must be a list of strings')
        item['skills']=sorted({normalise_skill(s) for s in skills if s.strip()})
        item['experience_level']=experience_level(item)
        docs.append(item)
    return docs

def doc_text(doc: dict[str,Any]) -> str:
    return doc['title']+' '+doc['role']+' '+doc['text']

@dataclass
class Hit:
    doc: dict[str,Any]
    score: float

class BM25:
    """Okapi BM25. `min_score` is the abstention threshold: weaker matches are treated as no evidence.

    With normalise=True a hit's score is divided by the query's maximum attainable BM25 score
    (sum of idf*(k1+1) over query terms; unseen terms count at the corpus's highest idf), so it reads as
    "share of the query's evidence weight this document matches" in [0, 1] and one threshold transfers
    across questions of different length.
    """
    def __init__(self,docs: list[dict[str,Any]], k1=1.5,b=0.75,stopwords=True,stemming=False,normalise=False,min_score=0.0):
        self.docs=docs; self.k1=k1; self.b=b; self.stopwords=stopwords; self.stemming=stemming
        self.normalise=normalise; self.min_score=min_score
        self.tokens=[tokenize(doc_text(d),stopwords,stemming) for d in docs]
        self.counts=[Counter(ts) for ts in self.tokens]
        self.avgdl=sum(map(len,self.tokens))/max(len(docs),1)
        df=Counter(t for ts in self.tokens for t in set(ts))
        self.idf={t: math.log(1+(len(docs)-n+0.5)/(n+0.5)) for t,n in df.items()}
        self.max_idf=max(self.idf.values(),default=1.0)
    def score_all(self,query: str,role: str|None=None) -> list[Hit]:
        q=set(tokenize(query,self.stopwords,self.stemming)); output=[]
        ceiling=sum(self.idf.get(t,self.max_idf) for t in q)*(self.k1+1) if self.normalise else 1.0
        for doc,counts,ts in zip(self.docs,self.counts,self.tokens):
            if role and doc['role'] != role: continue
            norm=self.k1*(1-self.b+self.b*len(ts)/max(self.avgdl,1))
            score=sum(self.idf[t]*counts[t]*(self.k1+1)/(counts[t]+norm) for t in q if counts[t])
            if score>0: output.append(Hit(doc,score/ceiling))
        return sorted(output,key=lambda h:(-h.score,h.doc['doc_id']))
    def search(self,query: str,role: str|None=None,k: int=5) -> list[Hit]:
        return [h for h in self.score_all(query,role) if h.score>=self.min_score][:k]

class DenseRetriever:
    """Optional dense retriever (exact cosine search). Downloads the embedding model on first use."""
    def __init__(self,docs: list[dict[str,Any]],model_name='sentence-transformers/all-MiniLM-L6-v2',min_score=0.0,encoder=None):
        import numpy as np
        self.np=np; self.docs=docs; self.min_score=min_score
        if encoder is None:
            from sentence_transformers import SentenceTransformer
            encoder=SentenceTransformer(model_name)
        self.model=encoder
        self.matrix=self._encode([doc_text(d) for d in docs]) if docs else np.zeros((0,1),dtype='float32')
    def _encode(self,texts):
        return self.np.asarray(self.model.encode(texts,normalize_embeddings=True,convert_to_numpy=True),dtype='float32')
    def score_all(self,query: str,role: str|None=None) -> list[Hit]:
        if not self.docs: return []
        scores=self.matrix@self._encode([query])[0]
        hits=[Hit(d,float(s)) for d,s in zip(self.docs,scores) if not role or d['role']==role]
        return sorted(hits,key=lambda h:(-h.score,h.doc['doc_id']))
    def search(self,query: str,role: str|None=None,k:int=5)->list[Hit]:
        return [h for h in self.score_all(query,role) if h.score>=self.min_score][:k]

class HybridRetriever:
    """Reciprocal Rank Fusion of BM25 and dense results that each pass their own threshold."""
    def __init__(self,bm25: BM25,dense: DenseRetriever,rrf_k=60):
        self.bm25=bm25; self.dense=dense; self.rrf_k=rrf_k; self.docs=bm25.docs
    def search(self,query: str,role: str|None=None,k: int=5) -> list[Hit]:
        fused={}; docs={}
        for retriever in (self.bm25,self.dense):
            for rank,hit in enumerate(retriever.search(query,role,k=len(retriever.docs))):
                fused[hit.doc['doc_id']]=fused.get(hit.doc['doc_id'],0)+1/(self.rrf_k+rank+1)
                docs[hit.doc['doc_id']]=hit.doc
        ranked=sorted(fused.items(),key=lambda pair:(-pair[1],pair[0]))[:k]
        return [Hit(docs[doc_id],score) for doc_id,score in ranked]

def build_retriever(docs,mode='bm25',encoder=None,**params):
    """params as written to results/best_config.json; hybrid takes {'bm25': {...}, 'dense': {...}}."""
    if mode=='bm25': return BM25(docs,**params)
    if mode=='dense': return DenseRetriever(docs,encoder=encoder,**params)
    if mode=='hybrid':
        dense=DenseRetriever(docs,encoder=encoder,**params.get('dense',{}))
        return HybridRetriever(BM25(docs,**params.get('bm25',{})),dense)
    raise ValueError('Choose bm25, dense or hybrid')

def gaps_from_evidence(hits:list[Hit],user_skills:list[str])->list[dict[str,Any]]:
    """One vote per source document; never infer absent skills from free-form text."""
    owned={normalise_skill(s).casefold() for s in user_skills}
    evidence={}
    for hit in hits:
        for skill in set(hit.doc.get('skills',[])):
            if skill.casefold() not in owned:
                evidence.setdefault(skill,set()).add(hit.doc['doc_id'])
    return [{'skill':skill,'supporting_document_ids':sorted(ids),'support_count':len(ids)}
            for skill,ids in sorted(evidence.items(),key=lambda pair:(-len(pair[1]),pair[0]))]

def role_skill_profile(docs:list[dict[str,Any]],role:str)->list[dict[str,Any]]:
    """How many of the role's documents name each skill. Independent of how a question is worded."""
    role_docs=[d for d in docs if d['role']==role]
    evidence={}
    for doc in role_docs:
        for skill in doc.get('skills',[]):
            evidence.setdefault(skill,set()).add(doc['doc_id'])
    return [{'skill':skill,'supporting_document_ids':sorted(ids),'support_count':len(ids),
             'role_document_count':len(role_docs),'share':len(ids)/len(role_docs)}
            for skill,ids in sorted(evidence.items(),key=lambda pair:(-len(pair[1]),pair[0]))]

def parse_user_skills(text:str|list[str])->set[str]:
    """Skills a user says they have, however they type them: "SQL Server, MS Excel", "Python and SQL",
    "Python/SQL/Excel", one per line. Known skills are found anywhere in the text with the same taxonomy used to
    tag the ads (case-insensitive here, since users often type "excel" or "r"); anything else is kept as typed."""
    text=text if isinstance(text,str) else ', '.join(text)
    items=[x.strip() for x in re.split(r'[,;/|\n]+|\band\b|&',text,flags=re.I) if x.strip()]
    def known_in(item):
        key=_alias_key(item)
        return {canon for canon,forms in SKILL_TAXONOMY.items() for f in forms+[canon]
                if key==_alias_key(f) or (len(_alias_key(f))>1 and
                    re.search(r'(?<![a-z0-9])'+re.escape(_alias_key(f))+r'(?![a-z0-9+#])',key))}
    found=set(extract_skills(text))
    for item in items:
        known=known_in(item)
        found|=known or {item}   # unknown skills are kept as typed, e.g. "Alteryx"
    return found

def gaps_for_role(docs:list[dict[str,Any]],role:str,user_skills:str|list[str],min_share:float=0.0)->list[dict[str,Any]]:
    owned={s.casefold() for s in parse_user_skills(user_skills)}
    return [row for row in role_skill_profile(docs,role) if row['skill'].casefold() not in owned and row['share']>=min_share]

# Words that only say "tell me about this role in general". A question made up solely of these (after
# stopword removal) is about the whole role, which keyword search over single ads cannot answer: the
# words appear in almost every ad, so no ad clears the abstention threshold.
OVERVIEW_WORDS = frozenset(stem(w) for w in """
skill skills requirement requirements required require requires requested request need needs needed ask asked
want wanted expect expected look looking role roles job jobs position positions employer employers typical
typically common commonly most main key important top usually generally general technical soft graduate
graduates junior entry level data analyst analysts scientist scientists science business qualification
qualifications competency competencies tool tools experience knowledge
""".split())

def is_overview_question(question: str) -> bool:
    terms = tokenize(question, stopwords=True, stemming=True)
    return bool(terms) and all(t in OVERVIEW_WORDS for t in terms)

def role_overview(docs:list[dict[str,Any]],role:str,k:int=3,top_n:int=15)->tuple[list[Hit],str]:
    """Evidence for a role-level question: skill counts over ALL the role's ads, plus the k ads that name
    the most of the role's ten most common skills (the most representative ads)."""
    role_docs=[d for d in docs if d['role']==role]
    profile=role_skill_profile(docs,role)
    common={p['skill'] for p in profile[:10]}
    ranked=sorted(role_docs,key=lambda d:(-len(common & set(d['skills'])),d['doc_id']))[:k]
    hits=[Hit(d,len(common & set(d['skills']))/max(len(common),1)) for d in ranked]
    lines=[f"- {p['skill']}: named in {p['support_count']} of {p['role_document_count']} ads ({p['share']:.0%})" for p in profile[:top_n]]
    summary=(f"[SOURCE SKILL_PROFILE] Skills named across all {len(role_docs)} {role} ads in the knowledge base "
             "(SEEK Australia, April 2018):\n"+'\n'.join(lines))
    return hits,summary

def role_overview_answer(docs:list[dict[str,Any]],role:str,top_n:int=15)->str:
    """Format role-level skill frequencies as a cited answer without requiring model generation."""
    role_docs=[d for d in docs if d['role']==role]
    profile=role_skill_profile(docs,role)[:top_n]
    lines=[f"- {item['skill']}: named in {item['support_count']} of {item['role_document_count']} ads "
           f"({item['share']:.0%}) [SOURCE SKILL_PROFILE]" for item in profile]
    return (f"Skills named across all {len(role_docs)} {role} ads in the knowledge base "
            "(SEEK Australia, April 2018):\n"+'\n'.join(lines))

def make_context(hits:list[Hit],max_chars_each=4000)->str:
    return '\n\n'.join(f'[SOURCE {h.doc["doc_id"]}] {h.doc["title"]}\nRole: {h.doc["role"]}\nURL: {h.doc["source_url"]}\n{h.doc["text"][:max_chars_each]}' for h in hits)
