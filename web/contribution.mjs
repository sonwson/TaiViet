import { WordState } from './word-state.mjs';

// Shared controller for word and sentence contribution. No linguistic rules in UI.
export function contribution({prefix,form,sentence,api,node,notice}){
  const model=new WordState();let timer,source=null,work=Promise.resolve();
  const input=f=>document.getElementById(prefix+'-'+f);
  const status=document.getElementById(prefix+'-status');
  const choices=document.getElementById(prefix+'-choices');
  const meanings=sentence?null:document.getElementById(prefix+'-meanings');
  let meaningRequest=0;
  async function loadMeanings(){
    if(!meanings)return;
    const request=++meaningRequest,version=model.version;
    const tai=model.fields.tai.value.trim(),roman=model.fields.roman.value.trim();
    meanings.replaceChildren();if(!tai&&!roman)return;
    try{
      const d=await api('words/meanings?tai='+encodeURIComponent(tai)+'&roman='+encodeURIComponent(roman));
      if(request!==meaningRequest||version!==model.version)return;
      meanings.append(node('p','Nghĩa đã có trong từ điển','review-label'));
      const values=[...new Set((d.items||[]).map(r=>r.vietnamese_meaning))];
      for(const value of values)meanings.append(node('p',value));
      if(!values.length)meanings.append(node('p','Chưa có nghĩa cho từ này.','hint'));
    }catch(e){if(request===meaningRequest&&version===model.version)meanings.append(node('p','Chưa tải được nghĩa hiện có. Bạn vẫn có thể đóng góp.','hint'));}
  }
  const indicators={};
  for(const f of ['tai','roman']){
    const label=input(f).parentElement;
    indicators[f]=node('small','','hint');label.append(indicators[f]);
    const button=node('button','↻ Tạo lại','regenerate');button.type='button';
    button.setAttribute('aria-label','Tạo lại '+(f==='tai'?'chữ Tai':'phiên âm'));
    let armed=false;
    button.addEventListener('click',()=>{
      if(model.fields[f].manual&&!armed){armed=true;button.textContent='Thay phần đã sửa? Bấm để tạo lại';return;}
      armed=false;button.textContent='↻ Tạo lại';const from=f==='tai'?'roman':'tai';
      model.regenerate(from);source=from;sync();start();
    });label.append(button);
    input(f).addEventListener('input',event=>{
      model.input(f,event.target.value);sync();clearTimeout(timer);source=f;choices.replaceChildren();
      status.textContent='';if(!event.isComposing)timer=setTimeout(start,350);
      ++meaningRequest;meanings?.replaceChildren();
    });
    input(f).addEventListener('compositionend',()=>{clearTimeout(timer);timer=setTimeout(start,350);});
  }
  function sync(){for(const f of ['roman','tai']){input(f).value=model.fields[f].value;indicators[f].textContent=model.indicator(f);}}
  async function check(){
    if(sentence)return;
    const v=model.version;
    const d=await api('words/check',{tai:model.fields.tai.value,romanization:model.fields.roman.value});
    if(v===model.version&&d.consistency_status==='mismatch')status.textContent='Chữ Tai và phiên âm chưa khớp. Bạn vẫn có thể gửi nguyên văn để người duyệt kiểm tra.';
  }
  async function generate(from,version){
    const target=from==='roman'?'tai':'roman',value=model.fields[from].value;
    if(!value.trim())return;
    if(model.fields[target].manual){await check();return;}
    status.textContent='Đang chuyển…';
    try{
      const result=await api('engine',{direction:from,text:value,sentence});
      if(version!==model.version)return;
      const field=target==='tai'?'tai':'romanization';
      const candidates=new Map();
      for(const c of result.dictionary_candidates||[])candidates.set(c[field],c);
      for(const c of result.candidates||[])if(!candidates.has(c[field]))candidates.set(c[field],c);
      choices.replaceChildren();
      const list=[...candidates.values()];
      if(list.length){
        model.apply(from,version,list[0][field]);sync();
        status.textContent=list[0].source==='dictionary_lookup'?'Đã điền theo từ điển. Bạn có thể sửa trực tiếp.':'Đã điền gợi ý. Bạn có thể sửa trực tiếp.';
      }
      if(list.length>1){
        const details=node('details');details.append(node('summary','Các cách viết / đọc khác'));
        const select=node('select');select.setAttribute('aria-label','Chọn gợi ý '+(target==='tai'?'chữ Tai':'phiên âm'));
        for(const c of list)select.append(new Option(c[field]+' · '+(c.source==='rule_based'?'quy tắc':'từ điển'),c[field]));
        select.value=list[0][field];
        select.addEventListener('change',()=>{if(select.value&&model.apply(from,version,select.value)){sync();status.textContent='Đã chọn gợi ý. Bạn có thể sửa trực tiếp.';loadMeanings();}});
        details.append(select);choices.append(details);
        if(result.truncated)choices.append(node('small','Danh sách đã giới hạn; bạn có thể nhập cách khác.','hint'));
      }else if(!list.length){
        status.textContent='Chưa đủ quy tắc để chuyển toàn bộ. Bạn có thể nhập hoặc gửi phần mình biết.';
        for(const t of result.tokens||[]){if(t.kind!=='word')continue;
          const a=node('p',t.text+' → '+(t.candidates?.map(c=>c[field]).slice(0,5).join(' / ')||'chưa rõ'),'hint');choices.append(a);
        }
      }
    }catch(e){if(version===model.version)status.textContent='Chưa chuyển được. Bạn vẫn có thể nhập và gửi.';}
  }
  function start(){clearTimeout(timer);if(source){const from=source;source=null;work=generate(from,model.version).then(loadMeanings);}return work;}
  return {
    async payload(){await start();return model.payload();},
    reset(){clearTimeout(timer);source=null;model.reset();sync();choices.replaceChildren();status.textContent='';++meaningRequest;meanings?.replaceChildren();}
  };
}
