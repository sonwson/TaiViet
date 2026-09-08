export function createAdminSelection({api, notice, reload}) {
  const $=id=>document.getElementById(id);
  const selected=new Set();
  let rows=[], filters=null, total=0, all=false, busy=false, deleteTarget='permanent';
  const toolbar=$('admin-selection');
  const dialog=$('admin-delete-dialog');
  const count=()=>all?total:selected.size;
  function update() {
    $('admin-selected-count').textContent=`Đã chọn ${count()} / ${total} bản ghi`;
    $('admin-select-page').checked=rows.length>0 && rows.every(r=>all||selected.has(r.id));
    $('admin-select-page').indeterminate=!all && selected.size>0 && selected.size<rows.length;
    $('admin-select-page').disabled=busy||!rows.length;
    $('admin-select-filtered').disabled=busy||!total||all;
    $('admin-select-filtered').textContent=`Chọn toàn bộ ${total} kết quả lọc`;
    $('admin-clear-selection').disabled=busy||!count();
    const isSentence=['sentences','translations','translation_validations','sentence_reviews','sentence_corrections','sentence_submissions','romanization_corrections'].includes(filters?.table);
    const isWord=filters?.table==='word_contributions';
    const subBtn=$('admin-delete-sub');
    if(subBtn) {
      subBtn.hidden=!(isSentence||isWord);
      subBtn.disabled=busy||!count();
      subBtn.textContent=isWord?'Xóa đóng góp đã chọn':'Xóa bản dịch đã chọn';
    }
    $('admin-delete-selected').disabled=busy||!count();
    $('admin-delete-selected').textContent='Xóa vĩnh viễn';
    document.querySelectorAll('.admin-row-check').forEach(input=>{
      input.checked=all||selected.has(input.value);
      input.disabled=busy;
      input.closest('article').classList.toggle('record-selected',input.checked);
    });
  }
  function clear() { selected.clear(); all=false; update(); }
  $('admin-select-page').addEventListener('change',e=>{
    all=false; selected.clear();
    if(e.target.checked) rows.forEach(r=>selected.add(r.id));
    update();
  });
  $('admin-select-filtered').addEventListener('click',()=>{all=true;selected.clear();update();});
  $('admin-clear-selection').addEventListener('click',clear);

  function openConfirm(target) {
    if(!count()||busy)return;
    deleteTarget=target;
    const label=$('admin-table').selectedOptions[0]?.textContent||filters?.table;
    const status=$('admin-status').selectedOptions[0]?.textContent||filters?.status;
    const isSub=target==='only_translations'||target==='only_contributions';
    if(isSub) {
      const itemNoun=target==='only_translations'?'bản dịch':'bản đóng góp';
      $('admin-delete-summary').textContent=`Xóa các ${itemNoun} thuộc ${count()} mục đã chọn trong “${label}” (${status})? ${all?'Phạm vi gồm toàn bộ kết quả lọc.':'Phạm vi chỉ gồm những mục được chọn trên trang này.'}`;
      $('admin-delete-warning').textContent=target==='only_translations'?'Chỉ các bản dịch liên quan bị xóa. Câu gốc tiếng Tai vẫn được giữ lại trong cơ sở dữ liệu.':'Chỉ các bản đóng góp này bị xóa. Từ trong từ điển vẫn được giữ lại.';
      $('admin-delete-confirm').textContent='Xóa đã chọn';
    } else {
      $('admin-delete-summary').textContent=`XÓA VĨNH VIỄN ${count()} bản ghi thuộc “${label}” (${status}) khỏi cơ sở dữ liệu? ${all?'Phạm vi gồm toàn bộ kết quả lọc, kể cả các trang khác.':'Phạm vi chỉ gồm những mục được chọn trên trang này.'}`;
      const notes={
        sentences:'Toàn bộ câu tiếng Tai và mọi bản dịch, đánh giá liên quan sẽ bị xóa sạch khỏi DB.',
        translations:'Cả câu gốc tiếng Tai và toàn bộ bản dịch liên quan sẽ bị xóa sạch khỏi DB.',
        translation_validations:'Xóa vĩnh viễn cả câu gốc tiếng Tai và mọi bản dịch liên quan khỏi DB.',
        sentence_reviews:'Xóa vĩnh viễn toàn bộ câu này cùng mọi bản dịch liên quan khỏi DB.',
        sentence_corrections:'Xóa vĩnh viễn toàn bộ câu này cùng mọi bản dịch liên quan khỏi DB.',
        sentence_submissions:'Xóa vĩnh viễn toàn bộ câu này cùng mọi bản dịch liên quan khỏi DB.',
        romanization_corrections:'Xóa vĩnh viễn toàn bộ câu này cùng mọi bản dịch liên quan khỏi DB.',
        word_contributions:'Xóa toàn bộ từ này trong từ điển và toàn bộ đóng góp liên quan khỏi DB.'
      };
      $('admin-delete-warning').textContent=(notes[filters.table]||'Toàn bộ dữ liệu liên quan sẽ bị xóa sạch khỏi cơ sở dữ liệu.')+' Thao tác này không thể hoàn tác!';
      $('admin-delete-confirm').textContent='Xóa vĩnh viễn';
    }
    dialog.showModal();
    $('admin-delete-cancel').focus();
  }

  $('admin-delete-sub')?.addEventListener('click',()=>{
    openConfirm(filters?.table==='word_contributions'?'only_contributions':'only_translations');
  });
  $('admin-delete-selected').addEventListener('click',()=>{
    openConfirm('permanent');
  });
  $('admin-delete-cancel').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
  $('admin-delete-confirm').addEventListener('click',async()=>{
    if(busy||!count())return;
    busy=true; update();
    $('admin-delete-confirm').disabled=true;
    $('admin-delete-cancel').disabled=true;
    $('admin-delete-confirm').textContent='Đang xóa…';
    try {
      const result=await api('admin/delete',{...filters,target:deleteTarget,scope:all?'filtered':'selected',ids:[...selected],expected_count:count()});
      dialog.close(); clear();
      await reload();
      notice(`Đã xóa ${result.deleted} bản ghi và dữ liệu liên quan.`);
    } catch(e) { dialog.close(); notice(e.message,true); }
    finally {
      busy=false; update();
      $('admin-delete-confirm').disabled=false;
      $('admin-delete-cancel').disabled=false;
      $('admin-delete-confirm').textContent='Xóa vĩnh viễn';
    }
  });
  return {
    reset() { filters=null;rows=[];total=0;clear();toolbar.hidden=true; },
    setPage(items, size, applied) { rows=items;total=size;filters=applied;clear();toolbar.hidden=['moderation_events','user_accounts'].includes(applied.table); },
    addRow(article, row) {
      if(!filters||['moderation_events','user_accounts'].includes(filters.table))return;
      const label=document.createElement('label');label.className='admin-row-select';label.title='Chọn bản ghi';
      const input=document.createElement('input');input.type='checkbox';input.className='admin-row-check';input.value=row.id;input.setAttribute('aria-label','Chọn bản ghi');
      label.append(input);article.prepend(label);
      input.addEventListener('change',()=>{
        if(all){all=false;rows.forEach(r=>selected.add(r.id));}
        if(input.checked)selected.add(row.id);else selected.delete(row.id);
        update();
      });
    }
  };
}
