from datetime import datetime, timezone
import json
from types import SimpleNamespace

from app.api import device_admin
from app.devices import mavlink_bridge
from test_drone_registry import _client
from app.access.principal import StationRole


def test_preview_requires_launch_and_send_requires_matching_review(monkeypatch):
    client, repo = _client(monkeypatch, StationRole.STATION_ADMIN)
    repo.drones['d-1'].update(lake_id='test-drone-field', credential_state='active')
    base = '/api/stations/st-1/inventory/d-1'
    params = {'home_lat': 47.5915, 'home_lon': -122.033, 'altitude_m': 20}
    assert client.post(base+'/patrol', json={}).status_code == 422
    preview = client.post(base+'/mission-preview', json=params)
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert len(result['mission_hash']) == 64
    assert result['home'] == {'lat': params['home_lat'], 'lon': params['home_lon']}
    assert result['route'] and result['waypoint_count'] > 0
    assert client.post(base+'/patrol', json={**params, 'reviewed_hash': '0'*64}).status_code == 409
    sent = client.post(base+'/patrol', json={**params, 'reviewed_hash': result['mission_hash']})
    assert sent.status_code == 202, sent.text
    assert sent.json()['status'] == 'queued'
    status = client.get(base+'/patrol-commands/'+sent.json()['command_id'])
    assert status.status_code == 200 and status.json()['status'] == 'queued'


def test_bridge_retries_ack_without_uploading_mission_again(monkeypatch):
    calls=[]
    monkeypatch.setattr(mavlink_bridge, 'run_command', lambda *args: (calls.append(True) or ('accepted','uploaded')))
    command={'command_id':'patrol-1','command_type':'patrol','ack':True,'patrol_ack':True,
             'expires_at':'2999-01-01T00:00:00Z','mission':[]}
    cached={}
    reply=json.dumps({'commands':[command]})
    first=mavlink_bridge.handle_reply(None,1,{},reply,cached)
    second=mavlink_bridge.handle_reply(None,1,{},reply,cached)
    assert first == second and len(second)==1
    assert calls == [True]



def test_preview_and_download_share_route_and_parameter_changes_invalidate_review(monkeypatch, patrol_repository):
    client, repo = _client(monkeypatch, StationRole.STATION_ADMIN)
    repo.drones['d-1'].update(lake_id='test-drone-field', credential_state='active')
    base='/api/stations/st-1/inventory/d-1'
    params={'home_lat':47.5915,'home_lon':-122.033,'altitude_m':20}
    preview=client.post(base+'/mission-preview',json=params).json()
    exported=client.post(base+'/mission',json={**params,'zone_id':preview['zone_id']})
    rows=[line.split('\t') for line in exported.text.splitlines()[1:]]
    route=[{'lat':float(row[8]),'lon':float(row[9])} for row in rows if int(row[3]) in (16,22)]
    assert preview['route']==route
    assert client.post(base+'/patrol',json={**params,'altitude_m':25,'reviewed_hash':preview['mission_hash']}).status_code==409
    assert patrol_repository.commands=={}
    assert client.post(base+'/mission-preview',json={**params,'home_lon':122.033}).status_code==422
    assert client.post(base+'/mission-preview',json={**params,'altitude_m':121}).status_code==422


def test_latest_command_restores_after_new_browser_client_and_is_station_scoped(monkeypatch):
    client, repo=_client(monkeypatch,StationRole.STATION_ADMIN)
    repo.drones['d-1'].update(lake_id='test-drone-field',credential_state='active')
    base='/api/stations/st-1/inventory/d-1'
    assert client.get(base+'/patrol-commands/latest').json()=={'command':None}
    params={'home_lat':47.5915,'home_lon':-122.033,'altitude_m':20}
    preview=client.post(base+'/mission-preview',json=params).json()
    queued=client.post(base+'/patrol',json={**params,'reviewed_hash':preview['mission_hash']}).json()
    replacement,_=_client(monkeypatch,StationRole.STATION_ADMIN)
    assert replacement.get(base+'/patrol-commands/latest').json()['command_id']==queued['command_id']
    assert replacement.get('/api/stations/other/inventory/d-1/patrol-commands/latest').status_code==404


def test_signed_patrol_ack_is_bound_to_command_and_consumes_sequence(monkeypatch, patrol_repository):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import devices
    from app.devices import drone_link
    key=Ed25519PrivateKey.generate()
    class AuthRepository:
        def active_credential(self, drone_id):
            return {'credential_id':'cred-1','drone_id':drone_id,'station_id':'station-1',
                    'public_key':drone_link.public_key_b64url(key),'credential_state':'active'}
    monkeypatch.setattr(devices,'get_device_repository',lambda:AuthRepository())
    app=FastAPI(); app.include_router(devices.router)
    client=TestClient(app)
    row={'command_id':'cmd-1','drone_id':'d-1','station_id':'station-1','status':'delivered','expires_at':'2999-01-01T00:00:00+00:00'}
    patrol_repository.commands['cmd-1']=row
    def signed(path, body,sequence):
        raw=json.dumps(body).encode()
        _,timestamp=drone_link._now()
        return client.post(path,content=raw,headers=drone_link.signed_headers(key,'d-1',raw,sequence=sequence,timestamp=timestamp))
    path='/api/devices/d-1/patrol-commands/cmd-1/acknowledgements'
    assert signed(path,{'command_id':'other','status':'accepted'},1).status_code==422
    assert row['status']=='delivered'
    assert signed(path,{'command_id':'cmd-1','status':'accepted','detail':'Flight controller accepted mission'},2).status_code==202
    assert row['status']=='uploaded'
    assert signed(path,{'command_id':'cmd-1','status':'accepted'},2).status_code==409
    assert signed(path,{'command_id':'cmd-1','status':'accepted'},3).status_code==202
    assert signed(path,{'command_id':'cmd-1','status':'completed'},4).status_code==422


def test_bridge_persists_result_and_uses_signed_patrol_endpoint(monkeypatch,tmp_path):
    calls=[]
    monkeypatch.setattr(mavlink_bridge,'run_command',lambda *args:(calls.append(True) or ('accepted','uploaded')))
    command={'command_id':'mission','command_type':'patrol','patrol_ack':True,'ack':True,'expires_at':'2999-01-01T00:00:00Z'}
    path=str(tmp_path/'outcomes.json')
    cached={}
    reply=json.dumps({'commands':[command]})
    mavlink_bridge.handle_reply(None,1,{},reply,cached,persist=lambda:mavlink_bridge.save_outcomes(path,cached))
    restored=mavlink_bridge.load_outcomes(path)
    [(current,outcome,detail)]=mavlink_bridge.handle_reply(None,1,{},reply,restored)
    endpoint,body=mavlink_bridge.acknowledgement_request('d-1',current,outcome,detail)
    assert '/patrol-commands/mission/acknowledgements' in endpoint
    assert body=={'command_id':'mission','status':'accepted','detail':'uploaded'}
    assert calls==[True]


def test_bridge_never_uploads_expired_patrol(monkeypatch):
    calls=[]
    monkeypatch.setattr(mavlink_bridge,'run_command',lambda *args:calls.append(True))
    result=mavlink_bridge.handle_reply(None,1,{},json.dumps({'commands':[{'command_id':'expired','expires_at':'2000-01-01T00:00:00Z'}]}),{})
    assert result[0][1]=='rejected' and calls==[]


def test_durable_patrol_schema_is_service_only_and_binds_scope_sequence_and_expiry():
    from pathlib import Path
    sql=(Path(__file__).parents[3]/'supabase/migrations/0046_durable_patrol_commands.sql').read_text().lower()
    assert 'enable row level security' in sql and 'force row level security' in sql
    assert 'from public,anon,authenticated' in sql and 'to service_role' in sql
    assert 'for update' in sql and 'p_sequence<=credential.last_sequence' in sql
    assert "inventory.lake_id=command.lake_id" in sql
    assert "credential.credential_id=command.credential_id" in sql
    assert "expires_at<=now()" in sql and "status='expired'" in sql
    assert "then 'uploaded' else 'rejected' end" in sql
    assert 'private.record_workflow_audit' in sql


def test_heartbeat_delivery_rejects_a_layout_changed_since_review(monkeypatch,patrol_repository):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import devices
    from app.devices import drone_link
    key=Ed25519PrivateKey.generate()
    class AuthRepository:
        def active_credential(self,drone_id):
            return {'credential_id':'cred-1','drone_id':drone_id,'station_id':'station-1','public_key':drone_link.public_key_b64url(key)}
        def record_heartbeat(self,principal,heartbeat,received_at):
            return {'eligible':True,'lake_id':'test-drone-field','eligibility_changed':False}
    monkeypatch.setattr(devices,'get_device_repository',lambda:AuthRepository())
    monkeypatch.setattr(device_admin,'_assigned_drone',lambda *args:{'inventory_id':'d-1','lake_id':'test-drone-field'})
    monkeypatch.setattr(device_admin,'prepare_mission',lambda *args:(None,None,None,'changed-hash'))
    patrol_repository.commands['c-1']={'command_id':'c-1','drone_id':'d-1','station_id':'station-1','status':'queued',
        'expires_at':'2999-01-01T00:00:00+00:00','zone_id':'cell-0','home':{'lat':47.5915,'lon':-122.033},'altitude_m':20,'mission_hash':'old-hash'}
    app=FastAPI();app.include_router(devices.router)
    raw=json.dumps({'battery_percent':90,'health':'healthy','connected':True}).encode()
    sequence,timestamp=drone_link._now()
    response=TestClient(app).post('/api/devices/d-1/heartbeat',content=raw,
        headers=drone_link.signed_headers(key,'d-1',raw,sequence=sequence,timestamp=timestamp))
    assert response.status_code==202,response.text
    assert response.json()['commands']==[]
    assert patrol_repository.commands['c-1']['status']=='rejected'


def test_default_bridge_cache_is_outside_current_project_and_unknown_upload_does_not_repeat(monkeypatch,tmp_path):
    from pathlib import Path
    assert not Path(mavlink_bridge.default_outcome_file()).is_relative_to(Path.cwd())
    command={'command_id':'uncertain','command_type':'patrol','expires_at':'2999-01-01T00:00:00Z'}
    path=str(tmp_path/'nested'/'outcome.json')
    state={}
    def crash(*args): raise RuntimeError('bridge stopped during upload')
    monkeypatch.setattr(mavlink_bridge,'run_command',crash)
    import pytest
    with pytest.raises(RuntimeError):
        mavlink_bridge.handle_reply(None,1,{},json.dumps({'commands':[command]}),state,
            persist=lambda:mavlink_bridge.save_outcomes(path,state))
    restored=mavlink_bridge.load_outcomes(path)
    [(command,status,detail)]=mavlink_bridge.handle_reply(None,1,{},json.dumps({'commands':[command]}),restored)
    assert status=='rejected' and 'unknown' in detail
