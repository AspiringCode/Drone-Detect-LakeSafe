import {useEffect,useState} from 'react';
import {apiRequest} from '../lib/apiClient';
import {supabase} from '../lib/supabase';
import {AccessibleDialog} from './AccessibleDialog';

type Visibility={visible:boolean;lakes?:Array<{lake_id:string;name:string}>;published_lakes?:number};
export function StationPublicVisibility({stationId}:{stationId:string}) {
  const [value,setValue]=useState<Visibility | null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [attempt,setAttempt]=useState(0);
  const [confirm,setConfirm]=useState(false);
  const [saved,setSaved]=useState(false);
  const [publishMore,setPublishMore]=useState(false);
  useEffect(()=>{let active=true;setValue(null);setError('');void apiRequest<Visibility>(`/api/stations/${stationId}/public-visibility`,{},supabase).then(result=>{if(active)setValue(result);}).catch(()=>{if(active)setError('Public visibility could not be loaded.');});return()=>{active=false;};},[stationId,attempt]);
  async function save(){if(!value || busy)return;setBusy(true);setError('');setSaved(false);try{const result=await apiRequest<Visibility>(`/api/stations/${stationId}/public-visibility`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({visible:publishMore || !value.visible})},supabase);setValue({...value,...result});setSaved(true);setConfirm(false);}catch(error){setError(error instanceof Error?error.message:'Public visibility could not be saved.');}finally{setBusy(false);}}
  return <section className="workflow-card"><h2>Public lake pages</h2>
    {value ? <><p role="status"><strong>{value.visible?'Open to public viewers':'Closed to public viewers'}</strong>{saved?' · Saved':''}</p>
    <p>Controls this station’s lake pages, published notices and public patrol updates. Operator access and membership stay the same.</p>
    {value.lakes?.length ? <p className="field-help">Lakes: {value.lakes.map(l=>l.name).join(', ')}</p>:<p className="field-help">This station has no public lake pages yet.</p>}
    <p className="field-help">{value.published_lakes ?? 0} of {value.lakes?.length ?? 0} lakes have published pages. Newly added lakes stay private until published here.</p>
    <button className={value.visible?'button-secondary':undefined} disabled={busy} onClick={()=>{setPublishMore(false);setConfirm(true);}}>{value.visible?'Close public lake pages':'Open public lake pages'}</button>
    {value.visible && (value.published_lakes ?? 0)<(value.lakes?.length ?? 0) && <button className="button-secondary" disabled={busy} onClick={()=>{setPublishMore(true);setConfirm(true);}}>Publish additional lakes</button>}
    {confirm && <AccessibleDialog title={value.visible && !publishMore?'Close public lake pages?':'Open public lake pages?'} onClose={()=>{if(!busy)setConfirm(false);}}><p>{value.visible && !publishMore?'Hide this station’s lakes and public updates from public browsing. People who already viewed them may retain previously loaded information.':'Publish this station’s lake names and maps. Only published safety notices and generalized patrol updates are shown; device telemetry and operator records remain private.'}</p><div className="modal-actions"><button disabled={busy} onClick={()=>void save()}>{busy?'Saving…':value.visible && !publishMore?'Close pages':'Open pages'}</button><button className="button-secondary" disabled={busy} onClick={()=>setConfirm(false)}>Cancel</button></div></AccessibleDialog>}
    </>:!error && <p role="status">Loading public visibility…</p>}
    {error && <div role="alert"><p className="form-error">{error}</p>{!value && <button className="button-secondary" onClick={()=>setAttempt(v=>v+1)}>Retry public visibility</button>}</div>}
  </section>;
}
