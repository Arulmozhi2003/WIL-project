import json
import pytest
from skillgap.core import BM25,HybridRetriever,Hit,normalise_skill,gaps_from_evidence,gaps_for_role,extract_skills,tokenize,load_documents
from skillgap.evaluation import evaluate,summarise,score_question,tune_bm25,skill_extraction_eval,bootstrap_ci
from skillgap.generation import check_answer,ABSTAIN

def docs():
    return [{'doc_id':'x','title':'Graduate analyst','role':'analyst','text':'SQL Excel Power BI','skills':['SQL','Power BI']},
            {'doc_id':'y','title':'Graduate scientist','role':'scientist','text':'Python statistics machine learning','skills':['Python']},
            {'doc_id':'z','title':'Junior analyst','role':'analyst','text':'SQL Tableau reporting','skills':['SQL','Tableau']}]

def test_bm25_role_filter():
    hits=BM25(docs()).search('Power BI analyst',role='analyst',k=2)
    assert [h.doc['doc_id'] for h in hits][0]=='x' and all(h.doc['role']=='analyst' for h in hits)

def test_normalisation_and_gap():
    hits=BM25(docs()).search('SQL Power BI',role='analyst',k=1)
    gaps=gaps_from_evidence(hits,['sql'])
    assert [g['skill'] for g in gaps]==['Power BI']
    assert normalise_skill('PowerBI')=='Power BI'
    assert normalise_skill('power-bi')=='Power BI'
    assert normalise_skill('MS Excel')=='Excel'

def test_empty_retrieval():
    assert BM25(docs()).search('unicorn',role='analyst')==[]

def test_stopwords_only_query_abstains():
    # The starter baseline matched "What salary will this job pay" on function words alone.
    assert BM25(docs()).search('what is this for',role='analyst')==[]
    assert BM25(docs(),stopwords=False).search('what is this for',role='analyst')==[]  # no shared tokens here either

def test_threshold_abstains():
    bm=BM25(docs())
    top=bm.search('SQL',role='analyst')[0].score
    assert BM25(docs(),min_score=top+1).search('SQL',role='analyst')==[]

def test_tokenizer_keeps_programming_languages():
    assert tokenize('C++, C# and Node.js.')==['c++','c#','and','node.js']
    assert 'the' not in tokenize('the SQL',stopwords=True)

def test_extract_skills_exact_mentions_only():
    text='You will excel at stakeholder engagement. Experience with Excel, SQL (PostgreSQL) and R is required. PowerBI a plus.'
    assert extract_skills(text)==['Excel','Power BI','R','SQL','Stakeholder Management']
    assert extract_skills('Our R&D team values research')==[]
    assert extract_skills('Our programme')==[]
    assert extract_skills('Power-BI, T-SQL and scikit learn')==['Power BI','SQL','Scikit-learn']

def test_role_gaps_do_not_depend_on_question():
    gaps=gaps_for_role(docs(),'analyst',['sql'])
    assert [(g['skill'],g['support_count'],g['share']) for g in gaps]==[('Power BI',1,0.5),('Tableau',1,0.5)]
    assert gaps_for_role(docs(),'analyst',['sql'],min_share=0.6)==[]

def test_load_documents_rejects_string_skills(tmp_path):
    doc={'doc_id':'a','role':'r','title':'t','text':'x','skills':'SQL, Excel','source_url':'u','source_type':'s','collected_date':'2026-01-01'}
    (tmp_path/'a.json').write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='list of strings'):
        load_documents(tmp_path)

def test_metrics():
    row=score_question({'id':'q','question':'?','split':'dev','relevant_doc_ids':['b']},['a','b'],k=2)
    assert row['hit_at_k'] and row['rr']==0.5 and row['decision_correct']
    unans=score_question({'id':'u','question':'?','split':'dev','relevant_doc_ids':[]},['a'],k=2)
    assert not unans['decision_correct']
    s=summarise([row,unans])
    assert s['decision_accuracy']==0.5 and s['abstain_rate_unanswerable']==0.0

def test_tuning_learns_threshold_that_fixes_unanswerable():
    d=docs()+[{'doc_id':'w','title':'Graduate analyst job','role':'analyst','text':'job job SQL','skills':['SQL']}]
    dev=[{'id':'1','question':'Power BI dashboards','role':'analyst','relevant_doc_ids':['x'],'split':'dev'},
         {'id':'2','question':'Tableau reporting','role':'analyst','relevant_doc_ids':['z'],'split':'dev'},
         {'id':'3','question':'what salary will this job pay','role':'analyst','relevant_doc_ids':[],'split':'dev'}]
    before=evaluate(BM25(d).search,dev,2)['summary']
    best=tune_bm25(d,dev,2)['best']
    after=evaluate(BM25(d,**best).search,dev,2)['summary']
    assert before['abstain_rate_unanswerable']==0.0
    assert after['decision_accuracy']==1.0 and after['hit_rate_at_k']==1.0

def test_bootstrap_ci_bounds():
    rows=[score_question({'id':str(i),'question':'?','split':'test','relevant_doc_ids':['a']},['a'] if i%2 else ['b'],k=1) for i in range(10)]
    lo,hi=bootstrap_ci(rows,'mean_ndcg_at_k')
    assert 0<=lo<=0.5<=hi<=1

def test_hybrid_fuses_and_respects_thresholds():
    class Fake:
        def __init__(self,order,docs): self.order=order; self.docs=docs
        def search(self,q,role,k): return [Hit(d,1.0) for d in self.order][:k]
    d=docs()
    fused=HybridRetriever(Fake([d[0],d[2]],d),Fake([d[2]],d)).search('q',None,2)
    assert [h.doc['doc_id'] for h in fused]==['z','x']
    assert HybridRetriever(Fake([],d),Fake([],d)).search('q',None,2)==[]

def test_skill_extraction_eval():
    d=[{'doc_id':'a','text':'SQL and Tableau','skills':['SQL','Tableau'],'skills_source':'manual'},
       {'doc_id':'b','text':'Python','skills':['Python','Statistics'],'skills_source':'manual'}]
    r=skill_extraction_eval(d)
    assert r['precision']==1.0 and r['recall']==0.75 and r['errors'][0]['missed']==['Statistics']

def test_answer_checks():
    hits=[Hit(docs()[0],1.0)]
    assert check_answer('Needs SQL [SOURCE x].',hits)['citations_valid']
    bad=check_answer('Needs SQL [SOURCE q].',hits)
    assert not bad['citations_valid'] and bad['invalid_citations']==['q']
    assert check_answer(ABSTAIN,hits)['abstained']
    assert check_answer('SQL appears in N of the retrieved documents [SOURCE x].',hits)['placeholder_count']
    assert not check_answer('SQL appears in N of the retrieved documents [SOURCE x].',hits)['grounding_pass']
    assert check_answer('SQL appears in 1 of the retrieved documents [SOURCE x].',hits)['grounding_pass']

def test_rag_prompt_contains_retrieved_sources(monkeypatch):
    """Retrieval-augmented generation: every retrieved ad's text and id must reach the model."""
    from skillgap import generation
    sent={}
    class Reply:
        def raise_for_status(self): pass
        def json(self): return {'message':{'content':'Needs SQL [SOURCE x].'}}
    def fake_post(url,json,timeout):
        sent.update(json)
        sent['request_timeout']=timeout
        return Reply()
    monkeypatch.setattr(generation.requests,'post',fake_post)
    d=[{**x,'source_url':f"https://example.org/{x['doc_id']}"} for x in docs()]
    hits=BM25(d).search('SQL Tableau',role='analyst',k=2)
    assert len(hits)==2
    answer=generation.answer_with_ollama('Is SQL needed?',hits,role='analyst')
    user=sent['messages'][1]['content']
    assert all(f"[SOURCE {h.doc['doc_id']}]" in user and h.doc['text'] in user for h in hits)
    assert 'TARGET ROLE: analyst' in user and 'Is SQL needed?' in user
    assert 'ONLY' in sent['messages'][0]['content'] and sent['options']['temperature']==0
    assert sent['options']['num_predict']==512 and sent['request_timeout']==600
    assert check_answer(answer,hits)['citations_valid']

def test_rag_refuses_without_calling_model_when_nothing_retrieved(monkeypatch):
    from skillgap import generation
    def fail(*a,**k): raise AssertionError('model must not be called without evidence')
    monkeypatch.setattr(generation.requests,'post',fail)
    hits=BM25(docs(),min_score=99).search('SQL',role='analyst')
    assert hits==[] and generation.answer_with_ollama('Is SQL needed?',hits)==ABSTAIN

def test_overview_questions_are_detected_but_specific_ones_are_not():
    from skillgap.core import is_overview_question
    for q in ['What skills are requested for this role?','What does a business analyst do?','What technical skills do data analyst jobs ask for most?']:
        assert is_overview_question(q), q
    for q in ['What will data analyst salaries be in 2030?','Is a forklift licence required for this job?','Is SQL required?','What is the capital of France?','']:
        assert not is_overview_question(q), q

def test_role_overview_counts_all_role_ads_and_picks_representative_ads():
    from skillgap.core import role_overview,role_overview_answer
    hits,summary=role_overview(docs(),'analyst',k=1)
    assert summary.startswith('[SOURCE SKILL_PROFILE]') and 'SQL: named in 2 of 2 ads (100%)' in summary
    assert [h.doc['doc_id'] for h in hits]==['x']   # ties on common skills broken by doc_id
    answer=role_overview_answer(docs(),'analyst')
    assert '- SQL: named in 2 of 2 ads (100%) [SOURCE SKILL_PROFILE]' in answer
    assert check_answer(answer,hits,extra_ids=('SKILL_PROFILE',))['grounding_pass']
    assert check_answer('SQL is common [SOURCE SKILL_PROFILE].',hits,extra_ids=('SKILL_PROFILE',))['citations_valid']
    assert not check_answer('SQL is common [SOURCE SKILL_PROFILE].',hits)['citations_valid']

def test_abstention_only_when_answer_opens_with_refusal():
    from skillgap.generation import is_abstention
    assert is_abstention(ABSTAIN) and is_abstention('  '+ABSTAIN+' The sources do not mention it.')
    assert not is_abstention('Yes, roles exist [SOURCE x]. '+ABSTAIN)

def test_user_skills_recognised_in_any_format():
    from skillgap.core import parse_user_skills
    cases={'SQL Server, MS Excel, Tableau Desktop':{'SQL','Excel','Tableau'},
           'Python and SQL':{'Python','SQL'}, 'Python/SQL/Excel':{'Python','SQL','Excel'},
           'Power-BI; ETL':{'Power BI','ETL'}, 'python\nsql':{'Python','SQL'}, 'r, sas':{'R','SAS'},
           'data visualization, stats':{'Data Visualisation','Statistics'},
           'Machine learning (ML), stakeholder engagement':{'Machine Learning','Stakeholder Management'}}
    for typed,expected in cases.items():
        assert expected <= parse_user_skills(typed), (typed, parse_user_skills(typed))
    # words that merely contain a skill name are not that skill
    assert not {'Excel','Git','R'} & parse_user_skills('excellent digital marketing, research')

def test_gap_table_drops_every_skill_the_user_has():
    gaps=gaps_for_role(docs(),'analyst','I know SQL Server and Tableau Desktop')
    assert [g['skill'] for g in gaps]==['Power BI']

def test_experience_level_uses_explicit_wording_only():
    from skillgap.core import experience_level
    ad=lambda title,text:{'title':title,'text':text}
    assert experience_level(ad('Junior Data Analyst','Minimum 5 years experience'))=='2+ years'
    assert experience_level(ad('Data Analyst',"Minimum 5 years' experience in SQL"))=='2+ years'
    assert experience_level(ad('Analyst','3 years+ experience as a Business Analyst'))=='2+ years'
    assert experience_level(ad('Analyst','At least 5 years working with Informatica'))=='2+ years'
    assert experience_level(ad('Analyst','A track record (min 2 years’ experience) of models'))=='2+ years'
    # company age and contract length are not experience requirements
    assert experience_level(ad('Analyst','Operating for over 40 years. 2 years fixed term contract.'))=='Experience not stated'
    assert experience_level(ad('Graduate Data Analyst','No prior professional requirement is stated.'))=='Graduate/entry wording'
    assert experience_level(ad('Data Analyst','1 year of experience using SQL'))=='0–1 year'
    # ranges use the upper bound; these were real failure modes in the project dataset
    assert experience_level(ad('Finance Business Analyst','1 to 2 years of Finance experience'))=='2+ years'
    assert experience_level(ad('Junior to Mid Level Data Scientist','Experience (typically 1-4 years) in a similar analytics area'))=='2+ years'
    assert experience_level(ad('Data Analyst','0-1 years experience with reporting'))=='0–1 year'
    # title wording never overrides a conflicting numeric requirement
    assert experience_level(ad('Graduate Data Analyst','Graduate program; 3 years experience required'))=='2+ years'

def test_claim_evidence_rows_shows_exact_cited_source_text():
    from skillgap.generation import claim_evidence_rows
    hits=[Hit(docs()[0],1.0)]
    rows=claim_evidence_rows('SQL is requested [SOURCE x].',hits)
    assert len(rows)==1
    assert rows[0]['source_id']=='x'
    assert 'SQL' in rows[0]['evidence_excerpt']
    assert rows[0]['trace_status']=='CITED SOURCE SHOWN'


def test_claim_evidence_rows_flags_uncited_claim_and_supports_profile():
    from skillgap.generation import claim_evidence_rows
    hits=[Hit(docs()[0],1.0)]
    rows=claim_evidence_rows('SQL is common [SOURCE SKILL_PROFILE].\nPower BI is useful.',hits,
                             {'SKILL_PROFILE':'SQL: named in 10 of 12 ads (83%).'})
    assert rows[0]['source_id']=='SKILL_PROFILE' and '10 of 12' in rows[0]['evidence_excerpt']
    assert rows[1]['trace_status']=='NO CITATION'
