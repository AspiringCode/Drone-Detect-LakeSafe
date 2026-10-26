"""Durable second-aircraft investigation intents; positions come from signed telemetry only."""
from functools import lru_cache
from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from app.supabase_transport import create_server_client
from app.devices.repository import DeviceRepositoryError
from app.coordination.assignment import haversine_m
from app.models import DroneStatus


def select_second_drone(detector, location, drones):
    candidates = [d for d in drones if d.drone_id != detector and d.source == 'real'
                  and d.status == DroneStatus.PATROLLING and d.battery >= .3]
    return min(candidates, key=lambda d: haversine_m(d.pos, location)).drone_id if candidates else None


class InvestigationRepository:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise DeviceRepositoryError('Investigation service is unavailable')
        self.client = create_server_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def call(self, name, **values):
        try:
            return self.client.rpc(name, values).execute().data
        except Exception as exc:
            raise DeviceRepositoryError('Investigation service is unavailable') from exc

    def begin(self, lake_id, alert, drones):
        second=select_second_drone(alert.drone_id, alert.location, drones)
        origin=next(({'lat':d.pos.lat,'lon':d.pos.lon} for d in drones if d.drone_id==second),None)
        return self.call('begin_real_investigation', p_lake_id=lake_id, p_alert_id=alert.alert_id,
                         p_second=second,p_origin=origin)

    def states(self, lake_id):
        return self.call('real_investigation_states', p_lake_id=lake_id) or {}

    def review(self, lake_id, alert_id, actor, decision):
        return self.call('decide_operational_alert', p_lake_id=lake_id, p_alert_id=alert_id,
                         p_actor=actor, p_decision=decision)

    def pending(self, principal):
        return self.call('deliver_investigation_commands', p_drone_id=principal.drone_id,
                         p_credential_id=principal.credential_id) or []

    def acknowledge(self, principal, command_id, outcome, detail):
        return self.call('acknowledge_investigation_command', p_drone_id=principal.drone_id,
                         p_credential_id=principal.credential_id, p_command_id=command_id,
                         p_sequence=principal.sequence, p_status=outcome, p_detail=detail)


@lru_cache(maxsize=1)
def get_investigation_repository():
    return InvestigationRepository()
