import {createAdminSelection} from './admin-selection.mjs';

export const statusLabels={all:'Tất cả',pending:'Chờ duyệt',approved:'Đã duyệt',rejected:'Từ chối',correct:'Đúng (correct)',needs_correction:'Cần sửa (needs_correction)',incorrect:'Sai (incorrect)',natural:'Tự nhiên',problematic:'Có vấn đề',unsure:'Chưa chắc',deleted:'Đã xóa',edited:'Đã sửa',user:'Thành viên',admin:'Quản trị viên'};
export function statusesFor(table) {
  return ({translation_validations:['correct','needs_correction','incorrect'],sentence_reviews:['natural','problematic','unsure'],moderation_events:['approved','rejected','pending','deleted','edited'],user_accounts:['user','admin']})[table]||['pending','approved','rejected'];
}

export function createAdminWorkspace({api,node,notice,attachAutoMatch,loadStats}) {
  const $=id=>document.getElementById(id);
  let offset=0,revision=0,currentTable='',owner=null,items=[],total=0,editor=null,feedback=null;
  let view=localStorage.getItem('tai_admin_view')==='cards'?'cards':'list';
  const selection=createAdminSelection({api,notice,reload:()=>load(true)});
  const results=$('admin-results');
  const editable=new Set(['sentences','translations','word_contributions','sentence_corrections']);
  const moderated=new Set(['sentences','translations','word_contributions','sentence_corrections','sentence_submissions','romanization_corrections']);
  function button(label,action,cls='secondary') {
    const b=node('button',label,cls);b.type='button';
    b.addEventListener('click',async()=>{b.disabled=true;try{await action();}catch(e){notice(e.message,true);}finally{b.disabled=false;}});
    return b;
  }
  function setView(value) {
    view=value;localStorage.setItem('tai_admin_view',view);
    results.className='admin-records admin-view-'+view;
    $('admin-view-list').setAttribute('aria-pressed',String(view==='list'));
    $('admin-view-cards').setAttribute('aria-pressed',String(view==='cards'));
    results.querySelectorAll('.admin-record-detail').forEach(d=>{d.open=view==='cards';});
  }
  function configureStatus() {
    const table=$('admin-table').value;
    if(table===currentTable)return;
    currentTable=table;
    $('admin-status').replaceChildren(...['all',...statusesFor(table)].map(value=>{
      const option=node('option',statusLabels[value]);option.value=value;return option;
    }));
    $('admin-status').disabled=false;
    $('admin-status').value=moderated.has(table)?'pending':'all';
    $('admin-query').placeholder=table==='user_accounts'?'Tìm tên hoặc email…':'Tìm nội dung…';
  }
  function reset() {
    revision++;selection.reset();items=[];results.replaceChildren();
    $('admin-more').disabled=true;$('admin-prev').disabled=true;
    $('admin-result-count').textContent='';
  }
  async function load(first=false) {
    if(first)offset=0;
    configureStatus();reset();const request=revision;
    const filters={table:currentTable,status:$('admin-status').value,q:$('admin-query').value.trim(),contributor_id:owner?.id||''};
    $('admin-owner-filter').hidden=!owner;
    $('admin-owner-label').textContent=owner?'Đóng góp của '+owner.display_name:'';
    results.append(node('p','Đang tải dữ liệu…','empty-state'));
    try {
      const data=await api('admin/records?'+new URLSearchParams({...filters,offset}));
      if(request!==revision)return;
      items=data.items;total=data.total;
      if(!items.length&&offset>0){offset=Math.max(0,offset-30);return load();}
      results.replaceChildren();selection.setPage(items,total,filters);
      for(const row of items)render(row,filters.table);
      if(!items.length)results.append(node('p','Không có dữ liệu phù hợp với bộ lọc.','empty-state'));
      $('admin-result-count').textContent=total?`${offset+1}–${offset+items.length} / ${total} bản ghi`:'0 bản ghi';
      $('admin-prev').disabled=offset===0;
      $('admin-more').disabled=offset+items.length>=total;
      setView(view);loadStats();
    } catch(e) {
      if(request===revision){results.replaceChildren(node('p',e.message,'error'));notice(e.message,true);}
    }
  }
  function filterOwner(user,table) {
    owner=user;$('admin-table').value=table;$('admin-query').value='';currentTable='';
    configureStatus();$('admin-status').value='all';return load(true);
  }
  function render(row,table) {
    const article=node('article',undefined,'record admin-record');
    const title=row.display_name||row.suggested_tai_text||row.sentence_tai||row.tai_text_final||row.tai_text_original||row.vietnamese_text||row.vietnamese_meaning||row.id;
    const tai=table!=='user_accounts'&&Boolean(row.suggested_tai_text||row.sentence_tai||row.tai_text_final||row.tai_text_original);
    const main=node('div',undefined,'admin-record-main');
    main.append(node('h3',title,tai?'tai':''));
    const preview=row.email||row.romanization_final||row.romanization||row.romanization_original||row.suggested_romanization||row.vietnamese_text||row.suggested_translation||'';
    if(preview)main.append(node('p',preview,'admin-record-preview'));
    const meta=node('div',undefined,'admin-record-meta');
    const status=row.status||row.validation_status||row.naturalness||row.new_status||row.role;
    if(status)meta.append(node('span',statusLabels[status]||status,'status-badge status-'+status));
    if(row.contributor_account)meta.append(button(row.contributor_account.display_name,()=>filterOwner(row.contributor_account,table),'admin-owner-button'));
    else if(row.contributor_id)meta.append(node('span',row.contributor_name||'Khách / chưa có tài khoản','hint'));
    const date=new Date(row.created_at);if(!Number.isNaN(date.getTime()))meta.append(node('small',date.toLocaleDateString('vi-VN'),'hint'));
    main.append(meta);article.append(main);
    const actions=node('div',undefined,'admin-record-actions');
    if(table==='user_accounts') {
      for(const [kind,label] of [['word_contributions','Từ'],['sentences','Câu'],['translations','Bản dịch']])actions.append(button(`${label}: ${row.counts[kind]}`,()=>filterOwner(row,kind)));
    } else {
      if(editable.has(table))actions.append(button('Sửa',()=>openEditor(row,table)));
      if(moderated.has(table)) {
        if(row.status!=='approved')actions.append(button('Duyệt',async()=>{await api('admin/moderate',{table,id:row.id,status:'approved'});await load();notice('Đã duyệt bản ghi.');},''));
        if(row.status!=='rejected')actions.append(button('Từ chối',()=>openFeedback(row,table,true),'btn-reject'));
      }
      if(row.contributor_account)actions.append(button('Phản hồi',()=>openFeedback(row,table,false)));
      const isSentenceTable=['sentences','translations','translation_validations','sentence_reviews','sentence_corrections','sentence_submissions','romanization_corrections'].includes(table);
      if(isSentenceTable) {
        const sid=row.sentence_id||(table==='sentences'?row.id:null);
        const taiTxt=row.sentence_tai||row.tai_text_original||row.tai_text_final||row.suggested_tai_text||'';
        const viTxt=row.vietnamese_text||row.suggested_translation||'';

        if(table==='translation_validations'&&row.translation_id) {
          actions.append(button('Sửa bản dịch',()=>openEditor({id:row.translation_id,vietnamese_text:viTxt,sentence_tai:taiTxt,status:'approved'},'translations')));
        }

        if(table==='translations') {
          actions.append(button('Xóa bản dịch',async()=>{
            if(!confirm(`Xóa bản dịch "${viTxt}"? (Câu gốc vẫn được giữ lại trong DB).`))return;
            await api('admin/delete',{table:'translations',target:'only_translations',scope:'selected',ids:[row.id],expected_count:1});
            await load();notice('Đã xóa bản dịch.');
          },'btn-outline-danger'));
        } else if(table==='translation_validations'&&row.translation_id) {
          actions.append(button('Xóa bản dịch',async()=>{
            if(!confirm(`Xóa bản dịch "${viTxt}"? (Câu gốc vẫn được giữ lại trong DB).`))return;
            await api('admin/delete',{table:'translations',target:'only_translations',scope:'selected',ids:[row.translation_id],expected_count:1});
            await load();notice('Đã xóa bản dịch.');
          },'btn-outline-danger'));
        } else if(sid) {
          actions.append(button('Xóa bản dịch',async()=>{
            if(!confirm(`Xóa các bản dịch của câu "${taiTxt}"? (Câu gốc tiếng Tai vẫn được giữ lại trong DB).`))return;
            await api('admin/delete',{table:'sentences',target:'only_translations',scope:'selected',ids:[sid],expected_count:1});
            await load();notice('Đã xóa các bản dịch của câu.');
          },'btn-outline-danger'));
        }

        if(sid) {
          actions.append(button('Xóa vĩnh viễn',async()=>{
            if(!confirm(`XÓA VĨNH VIỄN: Xóa toàn bộ câu "${taiTxt}" cùng mọi bản dịch, đánh giá liên quan khỏi cơ sở dữ liệu? Thao tác này không thể hoàn tác!`))return;
            await api('admin/delete',{table:'sentences',target:'permanent',scope:'selected',ids:[sid],expected_count:1});
            await load();notice('Đã xóa vĩnh viễn câu khỏi cơ sở dữ liệu.');
          },'btn-danger'));
        }
      } else if(table==='word_contributions'||table==='lexemes') {
        const wordText=row.tai_text_final||row.tai_text_original||'';
        if(table==='word_contributions') {
          actions.append(button('Xóa đóng góp',async()=>{
            if(!confirm(`Chỉ xóa bản đóng góp này? (Từ trong từ điển vẫn giữ).`))return;
            await api('admin/delete',{table:'word_contributions',target:'only_contributions',scope:'selected',ids:[row.id],expected_count:1});
            await load();notice('Đã xóa bản đóng góp.');
          },'btn-outline-danger'));
        }
        if(wordText) {
          actions.append(button('Xóa vĩnh viễn',async()=>{
            if(!confirm(`XÓA VĨNH VIỄN: Xóa toàn bộ từ "${wordText}" (gồm mọi nghĩa trong từ điển và các đóng góp liên quan) khỏi cơ sở dữ liệu? Thao tác này không thể hoàn tác!`))return;
            await api('admin/words/delete-entire',{id:row.id,tai_text:wordText});
            await load();
            notice(`Đã xóa vĩnh viễn từ "${wordText}" khỏi cơ sở dữ liệu.`);
          },'btn-danger'));
        }
      }
    }
    article.append(actions);
    const details=node('details',undefined,'admin-record-detail');details.open=view==='cards';
    details.append(node('summary','Xem chi tiết'));
    for(const [key,label] of [['email','Email'],['tai_text_original','Chữ Tai gốc'],['tai_text_final','Chữ Tai'],['romanization','Phiên âm'],['vietnamese_text','Bản dịch'],['vietnamese_meaning','Nghĩa'],['suggested_translation','Bản dịch đề xuất'],['suggested_tai_text','Câu đề xuất'],['suggested_romanization','Phiên âm đề xuất'],['suggested_meaning','Nghĩa đề xuất'],['source_reference','Nguồn']])if(row[key])details.append(node('p',label+': '+row[key]));
    const raw=node('details');raw.append(node('summary','Dữ liệu và nguồn gốc'),node('pre',JSON.stringify(row,null,2)));details.append(raw);article.append(details);
    selection.addRow(article,row);results.append(article);
  }
  function field(container,key,label,value,{required=false,maxLength=5000,tai=false}={}) {
    const wrap=node('label',label),input=node('textarea',undefined,tai?'tai':'');
    input.name=key;input.value=value||'';input.required=required;input.maxLength=maxLength;input.rows=tai?2:3;
    wrap.append(input);container.append(wrap);return input;
  }
  function openEditor(row,table) {
    editor={row,table};const fields=$('admin-editor-fields');fields.replaceChildren();
    $('admin-editor-error').textContent='';$('admin-editor-title').textContent=table==='translations'?'Sửa bản dịch':'Sửa đóng góp';
    let tai,roman;
    if(table==='sentences') {
      tai=field(fields,'tai_text_original','Câu chữ Tai',row.tai_text_original,{required:true,tai:true});
      roman=field(fields,'romanization','Phiên âm',row.romanization,{required:true});
      fields.append(node('p','Chỉnh sửa nội dung câu. Mỗi bản dịch được sửa riêng trong loại dữ liệu “Bản dịch”.','hint'));
    } else if(table==='translations') {
      fields.append(node('p',row.sentence_tai||'','tai'));
      field(fields,'vietnamese_text','Nội dung bản dịch',row.vietnamese_text,{required:true});
    } else if(table==='word_contributions') {
      tai=field(fields,'tai_text','Chữ Tai',row.tai_text_final||row.tai_text_original,{required:true,maxLength:120,tai:true});
      roman=field(fields,'romanization','Phiên âm',row.romanization_final||row.romanization_original,{maxLength:120});
      field(fields,'vietnamese_meaning','Nghĩa tiếng Việt',row.vietnamese_meaning,{required:true});
    } else {
      tai=field(fields,'suggested_tai_text','Câu chữ Tai đề xuất',row.suggested_tai_text,{required:true,tai:true});
      roman=field(fields,'suggested_romanization','Phiên âm',row.suggested_romanization,{required:true});
      field(fields,'suggested_meaning','Nghĩa tiếng Việt',row.suggested_meaning,{required:true});
    }
    if(tai&&roman){const match=node('div',undefined,'auto-match-box');fields.append(match);attachAutoMatch(tai,roman,table!=='word_contributions',match);}
    const label=node('label','Trạng thái'),select=node('select');select.name='status';
    for(const status of ['pending','approved','rejected']){const option=node('option',statusLabels[status]);option.value=status;select.append(option);}select.value=row.status;
    label.append(select);fields.append(label);
    if(row.contributor_account)field(fields,'feedback',`Phản hồi cho ${row.contributor_account.display_name} (không bắt buộc)`,'',{maxLength:2000});
    $('admin-editor').showModal();fields.querySelector('textarea')?.focus();
  }
  $('admin-editor-form').addEventListener('submit',async e=>{
    e.preventDefault();if(!editor)return;
    const {row,table}=editor,form=e.currentTarget;
    const body={...Object.fromEntries(new FormData(form)),id:row.id,table};
    const path=table==='word_contributions'?'admin/words/edit':table==='sentence_corrections'?'admin/sentence-corrections/edit':'admin/records/edit';
    $('admin-editor-save').disabled=true;$('admin-editor-cancel').disabled=true;
    try{await api(path,body);$('admin-editor').close();await load();notice('Đã lưu thay đổi'+(body.feedback?.trim()?' và gửi phản hồi.':'.'));}
    catch(err){$('admin-editor-error').textContent=err.message;}
    finally{$('admin-editor-save').disabled=false;$('admin-editor-cancel').disabled=false;}
  });
  function openFeedback(row,table,reject) {
    feedback={row,table,reject};const account=row.contributor_account;
    $('admin-feedback-title').textContent=reject?'Từ chối đóng góp':'Phản hồi người đóng góp';
    $('admin-feedback-recipient').textContent=account?`Người nhận: ${account.display_name}`:'Người đóng góp chưa có tài khoản.';
    const message=$('admin-feedback-message');message.value='';message.disabled=!account;message.required=!reject;
    $('admin-feedback-help').textContent=account?(reject?'Lý do không bắt buộc. Nếu nhập, nội dung sẽ xuất hiện trong tài khoản của người đóng góp.':'Phản hồi được gửi vào tài khoản. Trạng thái duyệt được giữ nguyên.'):'Bạn vẫn có thể từ chối, nhưng không thể gửi phản hồi cho khách.';
    $('admin-feedback-send').textContent=reject?'Xác nhận từ chối':'Gửi phản hồi';
    $('admin-feedback-error').textContent='';$('admin-feedback-dialog').showModal();
    if(account)message.focus();else $('admin-feedback-cancel').focus();
  }
  $('admin-feedback-form').addEventListener('submit',async e=>{
    e.preventDefault();if(!feedback)return;
    const {row,table,reject}=feedback;
    const message=$('admin-feedback-message').value.trim();
    if(!reject&&!message){$('admin-feedback-error').textContent='Vui lòng nhập phản hồi.';return;}
    $('admin-feedback-send').disabled=true;$('admin-feedback-cancel').disabled=true;
    try{await api(reject?'admin/moderate':'admin/feedback',{table,id:row.id,status:'rejected',feedback:message});$('admin-feedback-dialog').close();await load();notice(reject?'Đã từ chối'+(message?' và gửi phản hồi.':'.'):'Đã gửi phản hồi.');}
    catch(err){$('admin-feedback-error').textContent=err.message;}
    finally{$('admin-feedback-send').disabled=false;$('admin-feedback-cancel').disabled=false;}
  });
  for(const [dialog,cancel,submit] of [['admin-editor','admin-editor-cancel','admin-editor-save'],['admin-feedback-dialog','admin-feedback-cancel','admin-feedback-send']]) {
    $(cancel).addEventListener('click',()=>$(dialog).close());
    $(dialog).addEventListener('cancel',e=>{if($(submit).disabled)e.preventDefault();});
  }
  $('admin-load').addEventListener('click',()=>load(true));
  $('admin-table').addEventListener('change',()=>{if($('admin-table').value==='user_accounts')owner=null;load(true);});
  $('admin-status').addEventListener('change',()=>load(true));
  $('admin-query').addEventListener('input',reset);
  $('admin-query').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();load(true);}});
  $('admin-more').addEventListener('click',()=>{offset+=30;load();});
  $('admin-prev').addEventListener('click',()=>{offset=Math.max(0,offset-30);load();});
  $('admin-owner-clear').addEventListener('click',()=>{owner=null;load(true);});
  $('admin-view-list').addEventListener('click',()=>setView('list'));
  $('admin-view-cards').addEventListener('click',()=>setView('cards'));
  return {load,reset};
}
