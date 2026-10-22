import json
from pathlib import Path
import streamlit as st
from skillgap.core import (load_documents,build_retriever,gaps_for_role,is_overview_question,role_overview,role_overview_answer,
                           parse_user_skills,LEVELS,EARLY_CAREER)
from skillgap.generation import answer_with_ollama,check_answer,claim_evidence_rows,best_evidence_excerpt,PROMPTS,DEFAULT_PROMPT

st.set_page_config(page_title='SkillGap',page_icon='🎯',layout='wide')
st.title('SkillGap — Evidence-grounded career navigator')
st.caption('Prototype: limited to the documents in the knowledge base. Not a hiring or career guarantee.')

@st.cache_data
def cached_docs(folder):
    return load_documents(folder)

@st.cache_resource
def cached_retriever(folder,mode,params_json,allowed_levels):
    # Build retrieval statistics over the selected evidence subset itself. This ensures an excluded
    # experienced ad cannot affect ranking/IDF for an early-career query.
    subset=[d for d in cached_docs(folder) if d['experience_level'] in allowed_levels]
    return build_retriever(subset,mode,**json.loads(params_json))

try:
    docs=cached_docs('data/documents')
except (ValueError,FileNotFoundError) as exc:
    st.error(f'Knowledge base error: {exc}');st.stop()
if not docs:
    st.warning('No documents yet. Add verified job or role documents in data/documents first.');st.stop()
if any(doc.get('source_type')=='SYNTHETIC_EXAMPLE' for doc in docs):
    st.error('DEMO DATA ONLY: synthetic examples are present. Do not use this knowledge base as evidence for Australian job-market claims.')

# Make provenance/age visible in the product rather than hiding it in the report.
dates=sorted({str(d.get('collected_date','')).strip() for d in docs if str(d.get('collected_date','')).strip()})
if dates:
    st.info(f"Knowledge base: {len(docs)} job ads; source collection dates {dates[0]} to {dates[-1]}. "
            "This prototype uses historical job-ad evidence, so it should not be interpreted as the current Australian market.")

config_path=Path('results/best_config.json')
tuned=json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else None
roles=sorted({d['role'] for d in docs})
role=st.selectbox('Target role',roles)

# Keep unknown-experience ads separate. They are not evidence of zero experience.
LEVEL_FILTERS={
    'Early-career candidate evidence (graduate/entry wording or explicit 0–1 year)':EARLY_CAREER,
    'Graduate/entry wording only (title signal, not verified 0 years)':('Graduate/entry wording',),
    'Explicit 0–1 year only':('0–1 year',),
    'Experience not stated (review separately)':('Experience not stated',),
    'All levels':LEVELS,
}
in_role=[d for d in docs if d['role']==role]
level_choice=st.radio('Job level',list(LEVEL_FILTERS),horizontal=False,
    format_func=lambda o:f"{o} ({sum(d['experience_level'] in LEVEL_FILTERS[o] for d in in_role)})",
    help=('Experience level is inferred only from explicit wording in each ad. A missing experience statement is not treated as zero experience. '
          'If graduate/junior wording conflicts with an explicit 2+ year requirement, the explicit requirement wins. Title wording alone is not proof of zero experience.'))
allowed=tuple(LEVEL_FILTERS[level_choice])
level_docs=[d for d in docs if d['experience_level'] in allowed]
role_docs=[d for d in level_docs if d['role']==role]
if not role_docs:
    st.warning('No ads for this role at this job level. Choose a wider level.');st.stop()
if len(role_docs)<5:
    st.warning(f'Only {len(role_docs)} ad(s) support this role/filter. Treat any skill-frequency result as very limited evidence.')

skills=st.text_input('Your existing skills (any format, e.g. "Python, SQL Server and Power BI")','Python, Excel')
question=st.text_area('Your question','What skills are requested for this role?')
with st.expander('Settings'):
    # The saved threshold was tuned on the original full 159-ad corpus. Filtering changes BM25 IDF and
    # score distributions, so silently reusing that threshold on a smaller subset would be invalid.
    using_full_corpus = level_choice == 'All levels'
    options=(['tuned'] if tuned and using_full_corpus else [])+['bm25','dense','hybrid']
    method=st.selectbox('Retriever',options,help=('"tuned" is available only for All levels because results/best_config.json '
        'was validated on the full corpus. Filtered subsets use an untuned retriever until separately evaluated.'))
    k=st.number_input('Evidence passages (max)',1,len(role_docs),min(tuned['k'] if tuned else 3,len(role_docs)))
    model=st.text_input('Ollama model','llama3.2:3b')
    prompt=st.selectbox('Prompt version',sorted(PROMPTS),index=sorted(PROMPTS).index(DEFAULT_PROMPT))
    min_share=st.slider('Only show gaps named in at least this share of role documents',0.0,1.0,0.0,0.05)

scope=f"{len(role_docs)} {role} ads" + ('' if level_choice=='All levels' else f" ({level_choice.lower()})")
if st.button('Analyse',type='primary'):
    mode,params=(tuned['mode'],tuned['params']) if method=='tuned' else (method,{})
    config_validated = bool(method=='tuned' and level_choice=='All levels')
    overview=is_overview_question(question); profile_text=None
    with st.spinner('Retrieving evidence...'):
        try:
            if overview:
                hits,profile_text=role_overview(level_docs,role,int(k))
            else:
                retriever=cached_retriever('data/documents',mode,json.dumps(params,sort_keys=True),allowed)
                hits=retriever.search(question,role,int(k))
        except Exception as exc:
            st.error(f'Retriever could not run: {exc}');st.stop()

    st.subheader('Answer')
    if overview:
        st.caption(f'Role-level question: answered from skill counts across all {scope} plus the {len(hits)} most representative ads.')

    result=None; checks=None
    if not hits:
        st.info('No document in the selected evidence subset matches this question closely enough, so SkillGap will not answer it. '
                'Try naming a specific skill, tool or task, choose a wider job level, or see the skill-gap table below.')
    else:
        if overview:
            result=role_overview_answer(level_docs,role)
        else:
            with st.spinner('Generating grounded answer...'):
                try:
                    result=answer_with_ollama(question,hits,model=model,role=role,prompt=prompt)
                except Exception as exc:
                    st.error('Ollama generation is unavailable. Verify Ollama is running and the model is installed. '+str(exc))
        if result:
            checks=check_answer(result,hits,extra_ids=('SKILL_PROFILE',) if overview else ())
            if checks['grounding_pass']:
                st.write(result)
            else:
                st.error('Grounding check failed, so SkillGap is withholding this generated answer from the final recommendation.')
                with st.expander('Show rejected generated draft'):
                    st.write(result)
            if checks['invalid_citations']:
                st.warning('The draft cites sources that were not retrieved: '+', '.join(checks['invalid_citations']))
            if checks['placeholder_count']:
                st.warning('The draft contains an unresolved count placeholder such as "N of the retrieved documents".')
            if not checks['abstained'] and not checks['has_citation']:
                st.warning('The draft contains no source citations and is therefore unsupported.')

    # Mentor-requested output proof: map each generated claim to the exact cited source text.
    if result and checks and checks['grounding_pass'] and not checks['abstained']:
        st.subheader('Evidence supporting this answer')
        extra_map={'SKILL_PROFILE':profile_text} if overview and profile_text else {}
        proof_rows=claim_evidence_rows(result,hits,extra_map)
        if proof_rows:
            st.dataframe(proof_rows,hide_index=True,use_container_width=True,
                column_config={
                    'claim':st.column_config.TextColumn('Answer claim',width='large'),
                    'source_id':st.column_config.TextColumn('Cited source'),
                    'evidence_excerpt':st.column_config.TextColumn('Exact evidence excerpt',width='large'),
                    'source_url':st.column_config.LinkColumn('Original source'),
                    'trace_status':st.column_config.TextColumn('Trace')
                })
            st.caption('This panel shows the source text attached to each cited claim so the output can be audited. '
                       'It proves traceability to the supplied evidence, but it does not automatically prove semantic faithfulness or correctness; those still require human review.')
        else:
            st.info('No claim-level citations were available to trace.')

    # Mentor-facing visible evaluation trace: show the steps, not only the generated answer.
    st.subheader('Evaluation trace')
    trace=[
        {'Step':'1. Scope filter','Result':f'{len(role_docs)} selected {role} ads','Status':'PASS' if role_docs else 'FAIL'},
        {'Step':'2. Retriever validation','Result':('Saved configuration evaluated on full corpus' if config_validated else 'Current filtered/subset configuration has not been separately validated'),
         'Status':('PASS' if config_validated else 'NOT VALIDATED')},
        {'Step':'3. Retrieval','Result':f'{len(hits)} evidence document(s) returned using {mode}','Status':'PASS' if hits else 'ABSTAIN'},
        {'Step':'4. Answer/refusal decision','Result':('Refused/abstained' if (checks and checks['abstained']) else ('Answered' if result else 'No generated answer')),
         'Status':('PASS' if (not hits and not result) or (checks and (checks['abstained'] or result)) else 'CHECK')},
        {'Step':'5. Citation presence','Result':('Yes' if checks and checks['has_citation'] else 'No'),
         'Status':('PASS' if checks and (checks['abstained'] or checks['has_citation']) else ('N/A' if not checks else 'FAIL'))},
        {'Step':'6. Citation ID validity','Result':('All cited IDs are in supplied evidence' if checks and checks['citations_valid'] else ('Not applicable' if checks and checks['abstained'] else 'Failed/not available')),
         'Status':('PASS' if checks and (checks['abstained'] or checks['citations_valid']) else ('N/A' if not checks else 'FAIL'))},
        {'Step':'7. Placeholder check','Result':('No unresolved placeholders' if checks and not checks['placeholder_count'] else ('Placeholder detected' if checks else 'Not applicable')),
         'Status':('PASS' if checks and not checks['placeholder_count'] else ('N/A' if not checks else 'FAIL'))},
    ]
    st.dataframe(trace,hide_index=True,use_container_width=True)
    st.caption('Runtime checks show filtering, retrieval and citation mechanics; they are not a substitute for held-out evaluation. Automatic citation validity checks only whether cited source IDs were supplied to the model. '
               'They do not prove that every claim is faithfully supported; faithfulness/correctness still require human evaluation.')

    st.subheader(f'Potential skill gaps across {scope}')
    owned=parse_user_skills(skills)
    if owned: st.caption('Skills recognised as yours (removed from this table): '+', '.join(sorted(owned)))
    gaps=gaps_for_role(level_docs,role,skills,min_share)
    if gaps:
        st.dataframe([{'Skill':g['skill'],'Documents naming it':f"{g['support_count']} of {g['role_document_count']}",
                       'Share':f"{g['share']:.0%}",'Example documents':', '.join(g['supporting_document_ids'][:5])+(' …' if g['support_count']>5 else '')} for g in gaps],
                     hide_index=True)
        st.caption('A potential gap means the skill is named in these selected documents and not in your list. It is not a judgement of your ability.')
        with st.expander('Show source proof for skill-gap table'):
            by_id={d['doc_id']:d for d in role_docs}
            proof=[]
            for g in gaps:
                for doc_id in g['supporting_document_ids'][:3]:
                    d=by_id.get(doc_id)
                    if not d: continue
                    proof.append({'Skill':g['skill'],'Source':doc_id,
                                  'Evidence excerpt':best_evidence_excerpt(d['text'],g['skill']),
                                  'Original source':d.get('source_url','')})
            if proof:
                st.dataframe(proof,hide_index=True,use_container_width=True,
                    column_config={'Evidence excerpt':st.column_config.TextColumn(width='large'),
                                   'Original source':st.column_config.LinkColumn()})
                st.caption('Up to three supporting ads are shown per skill. The skill tagger is taxonomy-based; this panel lets a reviewer inspect the actual source wording.')
    else:
        st.write('No additional skills were identified from the selected role documents.')

    if hits:
        st.subheader('Retrieved evidence')
        for hit in hits:
            d=hit.doc
            with st.expander(f"{d['doc_id']} — {d['title']} · {d['experience_level']} (score {hit.score:.3f})"):
                st.write(d['text']);st.write('Source:',d['source_url'],'· collected',d['collected_date'])
