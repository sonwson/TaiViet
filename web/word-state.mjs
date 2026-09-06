// Values typed by the contributor stay distinct from editable generated values.
export class WordState {
  constructor(){this.reset();}
  reset(){this.version=(this.version||0)+1;this.fields={roman:this.empty(),tai:this.empty()};}
  empty(){return {original:'',value:'',generated:null,generatedFrom:null,manual:false};}
  input(field,value){
    const current=this.fields[field],other=this.fields[field==='roman'?'tai':'roman'];
    current.original=value;current.value=value;current.manual=!!value.trim();
    if(!current.manual){current.generated=null;current.generatedFrom=null;}
    // A changed source invalidates the previous automatic target.
    if(!other.manual){other.value='';other.generated=null;other.generatedFrom=null;}
    return ++this.version;
  }
  apply(source,version,value){
    const target=this.fields[source==='roman'?'tai':'roman'];
    if(version!==this.version||target.manual)return false;
    target.value=value;target.generated=value||null;target.generatedFrom=this.fields[source].value;return true;
  }
  regenerate(source){
    const target=this.fields[source==='roman'?'tai':'roman'];
    target.manual=false;target.value='';target.generated=null;target.generatedFrom=null;
    return ++this.version;
  }
  indicator(field){
    const f=this.fields[field];
    return f.generated!==null?(f.generated===f.value?'Tự động suy ra':'Đã chỉnh sửa'):(f.original?'Bạn nhập':'');
  }
  payload(){const {tai,roman}=this.fields;return {
    tai_text_original:tai.original,romanization_original:roman.original,
    tai_text_final:tai.value,romanization_final:roman.value,
    tai_text_generated:tai.generated,romanization_generated:roman.generated,
    generation_inputs:{tai:tai.generatedFrom,roman:roman.generatedFrom}
  };}
}
