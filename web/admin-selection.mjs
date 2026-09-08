export function createAdminSelection({api, notice, reload}) {
  const $=id=>document.getElementById(id);
  const selected=new Set();
  let rows=[], filters=null, total=0, all=false, busy=false;
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
    $('admin-delete-selected').disabled=busy||!count();
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
  $('admin-delete-selected').addEventListener('click',()=>{
    if(!count()||busy)return;
    const label=$('admin-table').selectedOptions[0].textContent;
    const status=$('admin-status').selectedOptions[0].textContent;
    $('admin-delete-summary').textContent=`Xóa vĩnh viễn ${count()} bản ghi thuộc “${label}” (${status})${filters.q?`, nội dung “${filters.q}”`:''}? ${all?'Phạm vi gồm toàn bộ kết quả lọc, kể cả các trang khác.':'Phạm vi chỉ gồm những mục được chọn trên trang này.'}`;
    const notes={sentences:'Các bản dịch, kiểm tra bản dịch, đánh giá, chú thích, đề xuất sửa và ví dụ liên quan cũng bị xóa.',translations:'Các kiểm tra và ví dụ liên quan đến bản dịch cũng bị xóa.',word_contributions:'Chỉ xóa bản đóng góp. Từ đã đưa vào từ điển vẫn được giữ.',sentence_submissions:'Chỉ xóa nguồn gốc đóng góp. Câu Tai vẫn được giữ.',sentence_corrections:'Xóa đề xuất không hoàn tác nội dung đã được duyệt vào câu gốc.',romanization_corrections:'Xóa đề xuất không hoàn tác phiên âm đã được duyệt.'};
    $('admin-delete-warning').textContent=(notes[filters.table]||'')+' Thao tác này không thể hoàn tác.';
    dialog.showModal();
    $('admin-delete-cancel').focus();
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
      const result=await api('admin/delete',{...filters,scope:all?'filtered':'selected',ids:[...selected],expected_count:count()});
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
    setPage(items, size, applied) { rows=items;total=size;filters=applied;clear();toolbar.hidden=applied.table==='moderation_events'; },
    addRow(article, row) {
      if(!filters||filters.table==='moderation_events')return;
      const label=document.createElement('label');label.className='admin-row-select';
      const input=document.createElement('input');input.type='checkbox';input.className='admin-row-check';input.value=row.id;
      label.append(input,document.createTextNode('Chọn bản ghi'));article.prepend(label);
      input.addEventListener('change',()=>{
        if(all){all=false;rows.forEach(r=>selected.add(r.id));}
        if(input.checked)selected.add(row.id);else selected.delete(row.id);
        update();
      });
    }
  };
}
