import { accountUI } from '/static/accounts.mjs';
import { contribution } from '/static/contribution.mjs';
const $ = id => document.getElementById(id);
const hamburger=document.querySelector('.hamburger');const mainNav=$('main-nav');
if(hamburger)hamburger.addEventListener('click',()=>{const open=mainNav.classList.toggle('open');hamburger.setAttribute('aria-expanded',String(open));hamburger.textContent=open?'✕':'☰';});
const state={session:null,sentence:null,review:null,sentenceOffset:0,reviewOffset:0,dictOffset:0,adminOffset:0,transFilters:{status:'approved',source:'all',meaning:'all',roman:'all'},reviewFilters:{status:'approved',source:'all',roman:'all'}};
function notice(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
async function api(path,body){const jwt=localStorage.getItem('tai_admin_token');const headers={...(body===undefined?{}:{'Content-Type':'application/json'}),...(jwt?{'Authorization':'Bearer '+jwt}:{})};const response=await fetch('/api/'+path,{credentials:'same-origin',...(body===undefined?{headers}:{method:'POST',headers,body:JSON.stringify(body)})});const data=await response.json().catch(()=>({detail:'Máy chủ đang gặp sự cố. Vui lòng thử lại sau.'}));if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Dữ liệu không hợp lệ.');return data;}
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
async function refreshSession(){state.session=await api('session');const card=$('admin-login-card')||$('admin-login');if(card)card.hidden=state.session.admin;$('admin-workspace').hidden=!state.session.admin;memberUI.sessionChanged();}
function formData(form){return Object.fromEntries(new FormData(form));}
function wireForm(id,path,extend=()=>({}),after=()=>{}){
  $(id).addEventListener('submit',async event=>{
    event.preventDefault();
    const form=event.currentTarget,base=formData(form),controls=[...form.elements].map(e=>[e,e.disabled]);
    controls.forEach(([e])=>e.disabled=true);
    try{
      const p={...base,...await extend()};
      const result=await api(path,p);
      notice(result.message||'Đã lưu.');form.reset();after();
    }catch(e){notice(e.message,true);}
    finally{controls.forEach(([e,disabled])=>e.disabled=disabled);await refreshSession().catch(e=>notice(e.message,true));}
  });
}
document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>openTab(button.dataset.tab)));
async function openTab(id){if(mainNav){mainNav.classList.remove('open');if(hamburger){hamburger.setAttribute('aria-expanded','false');hamburger.textContent='☰';}}document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==id);document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===id)));history.replaceState(null,'','#'+id);notice('');try{if(id==='translate'&&!state.sentence)await loadSentence();if(id==='review'&&!state.review)await loadReview();if(id==='dictionary')await searchDictionary();if(id==='admin'&&state.session?.admin)await loadAdmin();await memberUI.open(id);}catch(e){notice(e.message,true);}}
const wordContribution=contribution({prefix:'word',form:$('word-form'),sentence:false,api,node,notice});
const sentenceContribution=contribution({prefix:'sentence',form:$('sentence-form'),sentence:true,api,node,notice});
wireForm('word-form','words',()=>wordContribution.payload(),()=>wordContribution.reset());
wireForm('sentence-form','sentences',()=>sentenceContribution.payload(),()=>sentenceContribution.reset());

function attachAutoMatch(taiEl,romEl,isSentence=false,container=null){
  let timer=null,activeSource=null;
  const hint=node('small','','auto-match-hint');
  if(container)container.append(hint);
  async function convert(from){
    const srcEl=from==='tai'?taiEl:romEl;
    const tgtEl=from==='tai'?romEl:taiEl;
    const val=srcEl.value.trim();
    if(!val){hint.textContent='';return;}
    hint.textContent='Đang tự động khớp…';
    try{
      const res=await api('engine',{direction:from,text:val,sentence:isSentence});
      const field=from==='tai'?'romanization':'tai';
      const cands=(res.candidates&&res.candidates.length)?res.candidates:(res.dictionary_candidates||[]);
      let matchedVal='';
      if(cands.length&&cands[0][field]){
        matchedVal=cands[0][field];
      }else if(res.tokens&&res.tokens.length){
        const parts=[];
        for(const t of res.tokens){
          if(t.kind==='word'){
            const tc=(t.candidates&&t.candidates.length)?t.candidates:(t.dictionary_candidates||[]);
            parts.push(tc[0]?tc[0][field]:t.text);
          }else parts.push(t.text);
        }
        matchedVal=parts.join('');
      }
      if(matchedVal){
        tgtEl.value=matchedVal;
        hint.textContent=cands.length>1?`✓ Đã khớp tự động: ${matchedVal} (${cands.length} gợi ý)`:`✓ Đã khớp tự động: ${matchedVal}`;
      }else{
        hint.textContent='Chưa có quy tắc tự động khớp cho phần này.';
      }
    }catch(e){hint.textContent='';}
  }
  const handle=(from)=>(e)=>{
    if(e.isComposing)return;
    clearTimeout(timer);
    activeSource=from;
    timer=setTimeout(()=>{if(activeSource===from)convert(from);},350);
  };
  taiEl.addEventListener('input',handle('tai'));
  taiEl.addEventListener('compositionend',handle('tai'));
  romEl.addEventListener('input',handle('roman'));
  romEl.addEventListener('compositionend',handle('roman'));
  return {convert,hint};
}

function sentenceCard(prompt,row,review=false){
  prompt.replaceChildren();
  prompt.append(node('p','Câu chữ Tai','review-label'),node('p',row.tai_text_original,'tai'),node('p','Phiên âm','review-label'));
  if(row.romanization)prompt.append(node('p',row.romanization,'review-romanization'));
  else prompt.append(node('p','Chưa có phiên âm duy nhất.','hint'));
  if(row.romanization_source==='generated_suggestion'){
    prompt.append(node('small','Gợi ý tự động theo quy tắc','hint'));
    const options=row.romanization_suggestions?.candidates||[];
    if(options.length>1){const detail=node('details');detail.append(node('summary','Xem các cách đọc'));for(const c of options.slice(0,20))detail.append(node('p',c.romanization));prompt.append(detail);}
    const unknown=row.romanization_suggestions?.unknown_tokens||[];
    if(unknown.length)prompt.append(node('p','Một số âm tiết chưa có quy tắc đủ rõ; bạn có thể bổ sung phiên âm.','hint'));
  }else if(row.romanization_source==='community_correction')prompt.append(node('small','Phiên âm cộng đồng đã duyệt','hint'));
  else if(row.romanization_source==='sentence_correction')prompt.append(node('small','Câu & phiên âm đã sửa','hint'));
  else if(row.romanization_source==='generated')prompt.append(node('small','Tự động suy ra khi đóng góp','hint'));
  else if(row.romanization_source==='generated_then_edited')prompt.append(node('small','Đã chỉnh sửa từ gợi ý tự động','hint'));

  const fullCorrection=node('details');
  const isAdmin=Boolean(state.session?.admin);
  fullCorrection.append(node('summary', isAdmin ? 'Sửa câu gốc, phiên âm & nghĩa (Admin)' : 'Đề xuất sửa câu gốc (kèm phiên âm & nghĩa)'));
  const fcBox=node('div',undefined,'correction-box');
  const taiLabel=node('label','Câu chữ Tai:');
  const taiInput=node('textarea',undefined,'tai');
  taiInput.rows=3; taiInput.maxLength=5000; taiInput.value=row.tai_text_original||'';
  taiLabel.append(taiInput);
  const romLabel=node('label','Phiên âm (bắt buộc):');
  const romInput=node('textarea');
  romInput.rows=2; romInput.maxLength=5000; romInput.value=row.romanization||'';
  romLabel.append(romInput);
  const matchBox=node('div',undefined,'auto-match-box');
  attachAutoMatch(taiInput,romInput,true,matchBox);
  const meanLabel=node('label','Nghĩa tiếng Việt (không bắt buộc):');
  const meanInput=node('textarea');
  meanInput.rows=3; meanInput.maxLength=5000;
  meanInput.value=(row.translations && row.translations[0]?.vietnamese_text) || row.vietnamese_text || '';
  meanLabel.append(meanInput);
  const btnSubmitCorr=node('button', isAdmin ? 'Lưu sửa câu gốc (Admin - Áp dụng ngay)' : 'Gửi đề xuất sửa câu gốc');
  btnSubmitCorr.type='button';
  btnSubmitCorr.addEventListener('click', async()=>{
    if(!taiInput.value.trim() || !romInput.value.trim()){
      notice('Vui lòng điền câu chữ Tai và phiên âm.', true);
      return;
    }
    btnSubmitCorr.disabled=true;
    try {
      const res = await api('sentence-corrections', {
        sentence_id: row.sentence_id || row.id,
        suggested_tai_text: taiInput.value.trim(),
        suggested_romanization: romInput.value.trim(),
        suggested_meaning: meanInput.value.trim()
      });
      notice(res.message || 'Đã gửi thành công.');
      fullCorrection.open=false;
      if (isAdmin) {
        if(review) await loadReview(); else await loadSentence();
      }
    } catch(e) { notice(e.message, true); }
    finally { btnSubmitCorr.disabled=false; }
  });
  fcBox.append(taiLabel, romLabel, matchBox, meanLabel, btnSubmitCorr);
  fullCorrection.append(fcBox);
  prompt.append(fullCorrection);

  if(review)prompt.append(node('p','Bản dịch cần kiểm tra','review-label'),node('p',row.vietnamese_text));
  else{
    prompt.append(node('p','Bản dịch hiện có','review-label'));
    const translations=row.translations||[];
    if(!translations.length)prompt.append(node('p','Chưa có bản dịch đã duyệt.','hint'));
    for(const t of translations)prompt.append(node('p',t.vietnamese_text));
  }
}
async function loadSentence(){
  const params=new URLSearchParams({
    limit: 1,
    offset: state.sentenceOffset,
    status: state.transFilters.status,
    source: state.transFilters.source,
    meaning: state.transFilters.meaning,
    roman: state.transFilters.roman
  });
  const d=await api('sentences?'+params.toString());
  state.sentence=d.items[0]||null;
  if(state.sentence)sentenceCard($('translation-prompt'),state.sentence);
  else $('translation-prompt').textContent='Không tìm thấy câu phù hợp với bộ lọc này.';
  $('translation-form').hidden=!state.sentence;
  $('naturalness-form').hidden=!state.sentence;
}
$('next-sentence').addEventListener('click',()=>{state.sentenceOffset++;loadSentence().catch(e=>notice(e.message,true));});
$('trans-filter-apply')?.addEventListener('click',()=>{
  state.transFilters={
    status: $('trans-filter-status').value,
    source: $('trans-filter-source').value,
    meaning: $('trans-filter-meaning').value,
    roman: $('trans-filter-roman').value
  };
  state.sentenceOffset=0;
  loadSentence().catch(e=>notice(e.message,true));
});
wireForm('translation-form','translations',()=>({sentence_id:state.sentence?.id}));
wireForm('naturalness-form','sentence-reviews',()=>({sentence_id:state.sentence?.id}));
async function loadReview(){
  const params=new URLSearchParams({
    limit: 1,
    offset: state.reviewOffset,
    status: state.reviewFilters.status,
    source: state.reviewFilters.source,
    roman: state.reviewFilters.roman
  });
  const d=await api('review-queue?'+params.toString());
  state.review=d.items[0]||null;
  if(state.review)sentenceCard($('review-prompt'),state.review,true);
  else $('review-prompt').textContent='Không có bản dịch phù hợp với bộ lọc này.';
  $('review-form').hidden=!state.review;
}
$('next-review').addEventListener('click',()=>{state.reviewOffset++;loadReview().catch(e=>notice(e.message,true));});
$('review-filter-apply')?.addEventListener('click',()=>{
  state.reviewFilters={
    status: $('review-filter-status').value,
    source: $('review-filter-source').value,
    roman: $('review-filter-roman').value
  };
  state.reviewOffset=0;
  loadReview().catch(e=>notice(e.message,true));
});
$('validation-status').addEventListener('change',()=>{const need=$('validation-status').value==='needs_correction';$('correction-label').hidden=!need;$('review-form').elements.suggested_translation.required=need;});
wireForm('review-form','validations',()=>({translation_id:state.review?.id}),()=>{state.reviewOffset=0;$('correction-label').hidden=true;$('review-form').elements.suggested_translation.required=false;loadReview().catch(e=>notice(e.message,true));});
async function searchDictionary(){const q=$('search-form').elements.q.value;const d=await api('dictionary?q='+encodeURIComponent(q)+'&offset='+state.dictOffset);$('dictionary-results').replaceChildren();for(const r of d.items){const article=node('article',undefined,'record');const h3=node('h3',r.tai_text_original,'tai');if(r.kind==='sentence'){const badge=node('span','Câu đã duyệt','dict-badge dict-badge-sentence');h3.append(badge);}else if(r.kind==='contribution'){const badge=node('span','Từ đóng góp','dict-badge dict-badge-contribution');h3.append(badge);}article.append(h3,node('p',r.romanization||'Chưa có phiên âm'),node('p',(r.part_of_speech?r.part_of_speech+' · ':'')+r.vietnamese_meaning));$('dictionary-results').append(article);}if(!d.items.length)$('dictionary-results').append(node('p','Không có kết quả.'));$('more-dictionary').disabled=!d.has_more;}
$('search-form').addEventListener('submit',e=>{e.preventDefault();state.dictOffset=0;searchDictionary().catch(e=>notice(e.message,true));});$('more-dictionary').addEventListener('click',()=>{state.dictOffset+=20;searchDictionary().catch(e=>notice(e.message,true));});
$('admin-login').addEventListener('submit',async e=>{e.preventDefault();try{const f=e.currentTarget.elements;const payload=f.token?{token:f.token.value}:{username:f.username?.value,password:f.password?.value};const res=await api('admin/login',payload);if(res.token)localStorage.setItem('tai_admin_token',res.token);e.currentTarget.reset();await refreshSession();await loadAdmin();notice('Đăng nhập thành công (JWT)!');}catch(e){notice(e.message,true);}});
$('admin-logout').addEventListener('click',async()=>{try{localStorage.removeItem('tai_admin_token');await api('admin/logout',{});await refreshSession();$('admin-results').replaceChildren();}catch(e){notice(e.message,true);}});
async function loadAdminStats(){try{const res=await api('admin/stats');const bar=$('admin-stats-bar');if(!bar)return;bar.replaceChildren();const titles={sentences:'Câu Tai',translations:'Bản dịch',word_contributions:'Từ đóng góp',sentence_corrections:'Sửa câu gốc',romanization_corrections:'Sửa phiên âm'};for(const[tbl,counts]of Object.entries(res.stats||{})){const card=node('div',undefined,'stat-card');card.append(node('strong',titles[tbl]||tbl));const countsDiv=node('div',undefined,'stat-counts');const pSpan=node('span',`Chờ: ${counts.pending||0} `,'pending');const aSpan=node('span',`· Duyệt: ${counts.approved||0}`,'approved');countsDiv.append(pSpan,aSpan);card.append(countsDiv);bar.append(card);}}catch(e){}}
async function loadAdmin(){await loadAdminStats();const table=$('admin-table').value;const d=await api('admin/records?table='+table+'&status='+$('admin-status').value+'&q='+encodeURIComponent($('admin-query').value)+'&offset='+state.adminOffset);$('admin-results').replaceChildren();for(const r of d.items){const article=node('article',undefined,'record');const titleText=r.suggested_tai_text||r.sentence_tai||r.tai_text_final||r.tai_text_original||r.vietnamese_text||r.vietnamese_meaning||r.id;const titleCls=(r.suggested_tai_text||r.sentence_tai||r.tai_text_final||r.tai_text_original)?'tai':'';article.append(node('h3',titleText,titleCls));const st=r.status||r.validation_status||r.naturalness||r.new_status;if(st){const badge=node('span',st==='approved'?'✓ Đã duyệt':st==='rejected'?'✕ Đã từ chối':st==='pending'?'⏳ Chờ duyệt':st,`status-badge status-${st}`);article.append(badge);}const fields=[['Chữ Tai',r.suggested_tai_text||r.sentence_tai||r.tai_text_final||r.tai_text_original],['Chữ Tai gốc',r.base_tai_text],['Phiên âm đề xuất',r.suggested_romanization],['Phiên âm gốc',r.base_romanization],['Phiên âm',r.romanization_final||r.romanization_original||r.romanization],['Bản dịch',r.vietnamese_text],['Ý nghĩa',r.suggested_meaning||r.vietnamese_meaning],['Nguồn',r.base_source||r.value_sources||r.source_type],['Kiểm tra',r.consistency_status]];for(const [label,value] of fields)if(value&&value!==titleText)article.append(node('p',label+': '+value));const detail=node('details');detail.append(node('summary','Xem dữ liệu và nguồn gốc'),node('pre',JSON.stringify(r,null,2)));article.append(detail);if(table==='word_contributions'){const editDet=node('details');editDet.append(node('summary','Sửa từ đóng góp (Admin)'));const edBox=node('div',undefined,'admin-edit-box');const tL=node('label','Chữ Tai');const tI=node('input',undefined,'tai');tI.value=r.tai_text_final||r.tai_text_original||'';tL.append(tI);const rL=node('label','Phiên âm');const rI=node('input');rI.value=r.romanization_final||r.romanization_original||'';rL.append(rI);const matchBox=node('div',undefined,'auto-match-box');attachAutoMatch(tI,rI,false,matchBox);const mL=node('label','Nghĩa tiếng Việt');const mI=node('textarea');mI.rows=2;mI.value=r.vietnamese_meaning||'';mL.append(mI);const btnSave=node('button','Lưu & Duyệt');btnSave.addEventListener('click',async()=>{btnSave.disabled=true;try{await api('admin/words/edit',{id:r.id,tai_text:tI.value.trim(),romanization:rI.value.trim(),vietnamese_meaning:mI.value.trim(),status:'approved'});await loadAdmin();notice('Đã cập nhật và duyệt từ đóng góp thành công!');}catch(e){notice(e.message,true);btnSave.disabled=false;}});edBox.append(tL,rL,matchBox,mL,btnSave);editDet.append(edBox);article.append(editDet);}if(table==='sentence_corrections'){const editDet=node('details');editDet.append(node('summary','Sửa câu đề xuất (Admin)'));const edBox=node('div',undefined,'admin-edit-box');const tL=node('label','Chữ Tai đề xuất');const tI=node('textarea',undefined,'tai');tI.rows=2;tI.value=r.suggested_tai_text||'';tL.append(tI);const rL=node('label','Phiên âm đề xuất');const rI=node('textarea');rI.rows=2;rI.value=r.suggested_romanization||'';rL.append(rI);const matchBox=node('div',undefined,'auto-match-box');attachAutoMatch(tI,rI,true,matchBox);const mL=node('label','Nghĩa tiếng Việt đề xuất');const mI=node('textarea');mI.rows=2;mI.value=r.suggested_meaning||'';mL.append(mI);const btnSave=node('button','Lưu & Duyệt');btnSave.addEventListener('click',async()=>{btnSave.disabled=true;try{await api('admin/sentence-corrections/edit',{id:r.id,suggested_tai_text:tI.value.trim(),suggested_romanization:rI.value.trim(),suggested_meaning:mI.value.trim(),status:'approved'});await loadAdmin();notice('Đã cập nhật và duyệt câu sửa thành công!');}catch(e){notice(e.message,true);btnSave.disabled=false;}});edBox.append(tL,rL,matchBox,mL,btnSave);editDet.append(edBox);article.append(editDet);}if(r.status){if(r.status==='approved'){const curr=node('button','✓ Đã duyệt','btn-current-status');curr.disabled=true;article.append(curr);const rej=node('button','Từ chối','btn-reject');rej.addEventListener('click',async()=>{rej.disabled=true;try{await api('admin/moderate',{table,id:r.id,status:'rejected'});await loadAdmin();notice('Đã chuyển sang từ chối.');}catch(e){notice(e.message,true);rej.disabled=false;}});article.append(rej);}else if(r.status==='rejected'){const app=node('button','Duyệt lại','');app.addEventListener('click',async()=>{app.disabled=true;try{await api('admin/moderate',{table,id:r.id,status:'approved'});await loadAdmin();notice('Đã duyệt lại bản ghi.');}catch(e){notice(e.message,true);app.disabled=false;}});article.append(app);const curr=node('button','✕ Đã từ chối','btn-current-status');curr.disabled=true;article.append(curr);}else{for(const [status,label]of[['approved','Duyệt'],['rejected','Từ chối']]){const b=node('button',label,status==='rejected'?'btn-reject':'');b.addEventListener('click',async()=>{b.disabled=true;try{await api('admin/moderate',{table,id:r.id,status});await loadAdmin();notice(status==='approved'?'Đã duyệt bản ghi.':'Đã từ chối bản ghi.');}catch(e){notice(e.message,true);b.disabled=false;}});article.append(b);}}}$('admin-results').append(article);}if(!d.items.length)$('admin-results').append(node('p','Không có bản ghi ở bộ lọc này.'));$('admin-more').disabled=d.items.length<30;}
$('admin-load').addEventListener('click',()=>{state.adminOffset=0;loadAdmin().catch(e=>notice(e.message,true));});$('admin-more').addEventListener('click',()=>{state.adminOffset+=30;loadAdmin().catch(e=>notice(e.message,true));});
$('btn-export-json')?.addEventListener('click',()=>{const t=$('export-table')?.value||'all',s=$('export-status')?.value||'approved';window.location.href=`/api/admin/export?format=json&table=${t}&status=${s}`;});
$('btn-export-csv')?.addEventListener('click',()=>{const t=$('export-table')?.value||'all',s=$('export-status')?.value||'approved';window.location.href=`/api/admin/export?format=csv&table=${t}&status=${s}&bom=true`;});
const memberUI=accountUI({api,node,state,refreshSession,openTab});
refreshSession().then(()=>{const tab=location.hash.slice(1).split('?')[0];return openTab(['words','sentences','translate','review','dictionary','about','admin','account','leaderboard','reset-password'].includes(tab)?tab:'words');}).catch(e=>notice('Không kết nối được ứng dụng: '+e.message,true));

for(const prefix of ['trans','review']) {
  const bar=$(prefix+'-filter-bar');
  const reset=node('button','Đặt lại','filter-reset');reset.type='button';
  reset.addEventListener('click',()=>{
    bar.querySelectorAll('select').forEach(select=>select.selectedIndex=0);
    $(prefix+'-filter-apply').click();
  });
  bar.append(reset);
}
