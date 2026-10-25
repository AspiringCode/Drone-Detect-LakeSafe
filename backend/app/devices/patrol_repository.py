"""Service-only durable patrol intent and signed upload acknowledgements."""
from functools import lru_cache
from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.supabase_transport import create_server_client
from app.devices.repository import DeviceRepositoryError


class PatrolRepository:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise DeviceRepositoryError('Patrol command service is unavailable')
        self.client = create_server_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def _rpc(self, name, values):
        try:
            return self.client.rpc(name, values).execute().data
        except Exception as exc:
            raise DeviceRepositoryError('Patrol command service is unavailable') from exc

    def queue(self, station_id, drone_id, lake_id, actor, payload):
        result = self._rpc('queue_real_patrol', {'p_station_id': station_id, 'p_drone_id': drone_id,
            'p_lake_id': lake_id, 'p_actor': actor, 'p_payload': payload})
        if not isinstance(result, dict) or not result:
            raise DeviceRepositoryError('Patrol command could not be queued')
        return result

    def status(self, station_id, drone_id, command_id):
        return self._rpc('real_patrol_status', {'p_station_id': station_id, 'p_drone_id': drone_id, 'p_command_id': command_id})

    def latest(self, station_id, drone_id):
        return self._rpc('latest_real_patrol', {'p_station_id': station_id, 'p_drone_id': drone_id})

    def pending(self, principal):
        return self._rpc('deliver_real_patrols', {'p_drone_id': principal.drone_id, 'p_credential_id': principal.credential_id}) or []

    def reject(self, principal, command_id, detail):
        self._rpc('reject_real_patrol', {'p_drone_id': principal.drone_id, 'p_command_id': command_id, 'p_detail': detail})

    def acknowledge(self, principal, command_id, status, detail):
        return self._rpc('acknowledge_real_patrol', {'p_drone_id': principal.drone_id, 'p_credential_id': principal.credential_id,
            'p_command_id': command_id, 'p_sequence': principal.sequence, 'p_status': status, 'p_detail': detail}) is True


@lru_cache(maxsize=1)
def get_patrol_repository():
    return PatrolRepository()
