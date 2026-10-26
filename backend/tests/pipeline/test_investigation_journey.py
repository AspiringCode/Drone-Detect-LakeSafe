from types import SimpleNamespace
from app import main
from app.models import Drone,DroneStatus,LatLon


def test_demo_observation_review_and_return_follow_one_incident(monkeypatch):
    runtime=main.build_lake_runtime('lake-sammamish')
    point=LatLon(47.6,-122.1)
    fleet=[Drone('sim-a',point,1,DroneStatus.IDLE,None),Drone('sim-b',LatLon(47.6001,-122.1),1,DroneStatus.IDLE,None)]
    runtime.engine.set_fleet(fleet,runtime.zones[:2])
    monkeypatch.setitem(main.lake_runtimes,runtime.lake_id,runtime)
    monkeypatch.setattr(main,'authorize_lake',lambda *a:SimpleNamespace(user_id='operator'))
    original={d.drone_id:d.pos for d in fleet}
    alert=main.demo_trigger(runtime.lake_id,None,main.DemoDetectionRequest(second_finding='observed'))
    assert alert['location']=={'lat':point.lat,'lon':point.lon}
    assert alert['investigation']['confirmer']=='sim-b'
    assert not alert['confirmed']
    runtime.engine.step(2)
    runtime.engine.step(3)
    latest=main.live_state(runtime,runtime.engine.step(0))['latest_alert']
    assert latest['confirmed'] and latest['review_decision'] is None
    result=main.review_alert(runtime.lake_id,alert['alert_id'],None,main.AlertDecision(decision='dismissed'))
    assert result['review_decision']=='dismissed' and result['investigation']['phase']=='returning'
    runtime.engine.step(2)
    assert {d.drone_id:d.pos for d in fleet}==original
    assert main.live_state(runtime,runtime.engine.step(0))['latest_alert']['investigation']['phase']=='returned'
