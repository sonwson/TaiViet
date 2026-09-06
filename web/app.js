import { contribution } from '/static/contribution.mjs';
const $ = id => document.getElementById(id);
const hamburger=document.querySelector('.hamburger');const mainNav=$('main-nav');
if(hamburger)hamburger.addEventListener('click',()=>{const open=mainNav.classList.toggle('open');hamburger.setAttribute('aria-expanded',String(open));hamburger.textContent=open?'✕':'☰';});
const state={session:null,sentence:null,review:null,sentenceOffset:0,reviewOffset:0,dictOffset:0,adminOffset:0};
function notice(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
async function api(path,body){const response=await fetch('/api/'+path,{credentials:'same-origin',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Dữ liệu không hợp lệ.');return data;}
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
async function refreshSession(){state.session=await api('session');const card=$('admin-login-card')||$('admin-login');if(card)card.hidden=state.session.admin;$('admin-workspace').hidden=!state.session.admin;}
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
async function openTab(id){if(mainNav){mainNav.classList.remove('open');if(hamburger){hamburger.setAttribute('aria-expanded','false');hamburger.textContent='☰';}}document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==id);document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===id)));history.replaceState(null,'','#'+id);notice('');try{if(id==='translate'&&!state.sentence)await loadSentence();if(id==='review'&&!state.review)await loadReview();if(id==='dictionary')await searchDictionary();if(id==='admin'&&state.session?.admin)await loadAdmin();}catch(e){notice(e.message,true);}}
const wordContribution=contribution({prefix:'word',form:$('word-form'),sentence:false,api,node,notice});
const sentenceContribution=contribution({prefix:'sentence',form:$('sentence-form'),sentence:true,api,node,notice});
wireForm('word-form','words',()=>wordContribution.payload(),()=>wordContribution.reset());
wireForm('sentence-form','sentences',()=>sentenceContribution.payload(),()=>sentenceContribution.reset());
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
  else if(row.romanization_source==='generated')prompt.append(node('small','Tự động suy ra khi đóng góp','hint'));
  else if(row.romanization_source==='generated_then_edited')prompt.append(node('small','Đã chỉnh sửa từ gợi ý tự động','hint'));
  const correction=node('details');correction.append(node('summary','Sửa / bổ sung phiên âm'));
  const label=node('label','Phiên âm của bạn');const input=node('textarea');input.maxLength=5000;input.rows=3;input.value=row.romanization||'';label.append(input);
  const send=node('button','Gửi phiên âm sửa');send.type='button';
  send.addEventListener('click',async()=>{send.disabled=true;try{await api('romanization-corrections',{sentence_id:row.sentence_id||row.id,suggested_romanization:input.value});notice('Đã gửi phiên âm sửa để duyệt.');correction.open=false;}catch(e){notice(e.message,true);}finally{send.disabled=false;}});
  correction.append(label,send);prompt.append(correction);
  if(review)prompt.append(node('p','Bản dịch cần kiểm tra','review-label'),node('p',row.vietnamese_text));
  else{
    prompt.append(node('p','Bản dịch hiện có','review-label'));
    const translations=row.translations||[];
    if(!translations.length)prompt.append(node('p','Chưa có bản dịch đã duyệt.','hint'));
    for(const t of translations)prompt.append(node('p',t.vietnamese_text));
  }
}
async function loadSentence(){const d=await api('sentences?limit=1&offset='+state.sentenceOffset);state.sentence=d.items[0]||null;
if(state.sentence)sentenceCard($('translation-prompt'),state.sentence);else $('translation-prompt').textContent='Chưa có câu đã duyệt ở trang này.';
$('translation-form').hidden=!state.sentence;$('naturalness-form').hidden=!state.sentence;}
$('next-sentence').addEventListener('click',()=>{state.sentenceOffset++;loadSentence().catch(e=>notice(e.message,true));});
wireForm('translation-form','translations',()=>({sentence_id:state.sentence?.id}));
wireForm('naturalness-form','sentence-reviews',()=>({sentence_id:state.sentence?.id}));
async function loadReview(){const d=await api('review-queue?limit=1&offset='+state.reviewOffset);state.review=d.items[0]||null;
if(state.review)sentenceCard($('review-prompt'),state.review,true);else $('review-prompt').textContent='Không có bản dịch cần kiểm tra ở trang này.';
$('review-form').hidden=!state.review;}
$('next-review').addEventListener('click',()=>{state.reviewOffset++;loadReview().catch(e=>notice(e.message,true));});
$('validation-status').addEventListener('change',()=>{const need=$('validation-status').value==='needs_correction';$('correction-label').hidden=!need;$('review-form').elements.suggested_translation.required=need;});
wireForm('review-form','validations',()=>({translation_id:state.review?.id}),()=>{state.reviewOffset=0;$('correction-label').hidden=true;$('review-form').elements.suggested_translation.required=false;loadReview().catch(e=>notice(e.message,true));});
async function searchDictionary(){const q=$('search-form').elements.q.value;const d=await api('dictionary?q='+encodeURIComponent(q)+'&offset='+state.dictOffset);$('dictionary-results').replaceChildren();for(const r of d.items){const article=node('article',undefined,'record');const h3=node('h3',r.tai_text_original,'tai');if(r.kind==='sentence'){const badge=node('span','Câu đã duyệt','dict-badge dict-badge-sentence');h3.append(badge);}else if(r.kind==='contribution'){const badge=node('span','Từ đóng góp','dict-badge dict-badge-contribution');h3.append(badge);}article.append(h3,node('p',r.romanization||'Chưa có phiên âm'),node('p',(r.part_of_speech?r.part_of_speech+' · ':'')+r.vietnamese_meaning));$('dictionary-results').append(article);}if(!d.items.length)$('dictionary-results').append(node('p','Không có kết quả.'));$('more-dictionary').disabled=d.items.length<20;}
$('search-form').addEventListener('submit',e=>{e.preventDefault();state.dictOffset=0;searchDictionary().catch(e=>notice(e.message,true));});$('more-dictionary').addEventListener('click',()=>{state.dictOffset+=30;searchDictionary().catch(e=>notice(e.message,true));});
$('admin-login').addEventListener('submit',async e=>{e.preventDefault();try{const f=e.currentTarget.elements;const payload=f.token?{token:f.token.value}:{username:f.username?.value,password:f.password?.value};await api('admin/login',payload);e.currentTarget.reset();await refreshSession();await loadAdmin();notice('Đăng nhập thành công!');}catch(e){notice(e.message,true);}});
$('admin-logout').addEventListener('click',async()=>{try{await api('admin/logout',{});await refreshSession();$('admin-results').replaceChildren();}catch(e){notice(e.message,true);}});
async function loadAdminStats(){try{const res=await api('admin/stats');const bar=$('admin-stats-bar');if(!bar)return;bar.replaceChildren();const titles={sentences:'Câu Tai',translations:'Bản dịch',word_contributions:'Từ đóng góp',romanization_corrections:'Sửa phiên âm'};for(const[tbl,counts]of Object.entries(res.stats||{})){const card=node('div',undefined,'stat-card');card.append(node('strong',titles[tbl]||tbl));const countsDiv=node('div',undefined,'stat-counts');const pSpan=node('span',`Chờ: ${counts.pending||0} `,'pending');const aSpan=node('span',`· Duyệt: ${counts.approved||0}`,'approved');countsDiv.append(pSpan,aSpan);card.append(countsDiv);bar.append(card);}}catch(e){}}
async function loadAdmin(){await loadAdminStats();const table=$('admin-table').value;const d=await api('admin/records?table='+table+'&status='+$('admin-status').value+'&q='+encodeURIComponent($('admin-query').value)+'&offset='+state.adminOffset);$('admin-results').replaceChildren();for(const r of d.items){const article=node('article',undefined,'record');const titleText=r.sentence_tai||r.tai_text_final||r.tai_text_original||r.vietnamese_text||r.vietnamese_meaning||r.id;const titleCls=(r.sentence_tai||r.tai_text_final||r.tai_text_original)?'tai':'';article.append(node('h3',titleText,titleCls));const st=r.status||r.validation_status||r.naturalness||r.new_status;if(st){const badge=node('span',st==='approved'?'✓ Đã duyệt':st==='rejected'?'✕ Đã từ chối':st==='pending'?'⏳ Chờ duyệt':st,`status-badge status-${st}`);article.append(badge);}const fields=[['Chữ Tai',r.sentence_tai||r.tai_text_final||r.tai_text_original],['Phiên âm đề xuất',r.suggested_romanization],['Phiên âm gốc',r.base_romanization],['Phiên âm',r.romanization_final||r.romanization_original||r.romanization],['Bản dịch',r.vietnamese_text],['Ý nghĩa',r.vietnamese_meaning],['Nguồn',r.base_source||r.value_sources||r.source_type],['Kiểm tra',r.consistency_status]];for(const [label,value] of fields)if(value&&value!==titleText)article.append(node('p',label+': '+value));const detail=node('details');detail.append(node('summary','Xem dữ liệu và nguồn gốc'),node('pre',JSON.stringify(r,null,2)));article.append(detail);if(r.status){if(r.status==='approved'){const curr=node('button','✓ Đã duyệt','btn-current-status');curr.disabled=true;article.append(curr);const rej=node('button','Từ chối','btn-reject');rej.addEventListener('click',async()=>{rej.disabled=true;try{await api('admin/moderate',{table,id:r.id,status:'rejected'});await loadAdmin();notice('Đã chuyển sang từ chối.');}catch(e){notice(e.message,true);rej.disabled=false;}});article.append(rej);}else if(r.status==='rejected'){const app=node('button','Duyệt lại','');app.addEventListener('click',async()=>{app.disabled=true;try{await api('admin/moderate',{table,id:r.id,status:'approved'});await loadAdmin();notice('Đã duyệt lại bản ghi.');}catch(e){notice(e.message,true);app.disabled=false;}});article.append(app);const curr=node('button','✕ Đã từ chối','btn-current-status');curr.disabled=true;article.append(curr);}else{for(const [status,label]of[['approved','Duyệt'],['rejected','Từ chối']]){const b=node('button',label,status==='rejected'?'btn-reject':'');b.addEventListener('click',async()=>{b.disabled=true;try{await api('admin/moderate',{table,id:r.id,status});await loadAdmin();notice(status==='approved'?'Đã duyệt bản ghi.':'Đã từ chối bản ghi.');}catch(e){notice(e.message,true);b.disabled=false;}});article.append(b);}}}$('admin-results').append(article);}if(!d.items.length)$('admin-results').append(node('p','Không có bản ghi ở bộ lọc này.'));$('admin-more').disabled=d.items.length<30;}
$('admin-load').addEventListener('click',()=>{state.adminOffset=0;loadAdmin().catch(e=>notice(e.message,true));});$('admin-more').addEventListener('click',()=>{state.adminOffset+=30;loadAdmin().catch(e=>notice(e.message,true));});
$('btn-export-json')?.addEventListener('click',()=>{const t=$('export-table')?.value||'all',s=$('export-status')?.value||'approved';window.location.href=`/api/admin/export?format=json&table=${t}&status=${s}`;});
$('btn-export-csv')?.addEventListener('click',()=>{const t=$('export-table')?.value||'all',s=$('export-status')?.value||'approved';window.location.href=`/api/admin/export?format=csv&table=${t}&status=${s}&bom=true`;});
refreshSession().then(()=>{const tab=location.hash.slice(1);return openTab(['words','sentences','translate','review','dictionary','about','admin'].includes(tab)?tab:'words');}).catch(e=>notice('Không kết nối được ứng dụng: '+e.message,true));
