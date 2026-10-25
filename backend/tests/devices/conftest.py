"""Local durable-queue double; production always uses service-only database RPCs."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.api import device_admin, devices
from app.devices.repository import DeviceRepositoryError


class FakePatrolRepository:
    def __init__(self):
        self.commands = {}
        self.sequences = {}

    def queue(self, station_id, drone_id, lake_id, actor, payload):
        row = {**payload, 'station_id': station_id, 'drone_id': drone_id, 'lake_id': lake_id,
               'command_id': str(uuid4()), 'status': 'queued', 'expires_at': (datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat()}
        self.commands[row['command_id']] = row
        return self.dto(row)

    def dto(self, row):
        if row['status'] in ('queued','delivered') and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc):
            row['status'] = 'expired'
        return {key: row[key] for key in ('command_id','status','expires_at','detail') if key in row}

    def status(self, station_id, drone_id, command_id):
        row = self.commands.get(command_id)
        return self.dto(row) if row and (row['station_id'],row['drone_id']) == (station_id,drone_id) else None

    def latest(self, station_id, drone_id):
        rows=[row for row in self.commands.values() if (row['station_id'],row['drone_id']) == (station_id,drone_id)]
        return self.dto(rows[-1]) if rows else None

    def pending(self, principal):
        rows=[]
        for row in self.commands.values():
            self.dto(row)
            if row['drone_id'] == principal.drone_id and row['status'] in ('queued','delivered'):
                row['status']='delivered'
                rows.append({**row,'ack':True,'patrol_ack':True,'command_type':'patrol'})
        return rows

    def reject(self, principal, command_id, detail):
        self.commands[command_id].update(status='rejected',detail=detail)

    def acknowledge(self, principal, command_id, status, detail):
        row=self.commands.get(command_id)
        if not row or row['drone_id']!=principal.drone_id or row['station_id']!=principal.station_id or self.dto(row)['status'] not in ('delivered','uploaded','rejected'):
            return False
        if principal.sequence <= self.sequences.get(principal.drone_id,-1): return False
        self.sequences[principal.drone_id]=principal.sequence
        row.update(status='uploaded' if status=='accepted' else 'rejected',detail=detail)
        return True


@pytest.fixture(autouse=True)
def patrol_repository(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "get_alert_review_repository", lambda: SimpleNamespace(reviewed_alerts=lambda _: {}))
    repository=FakePatrolRepository()
    monkeypatch.setattr(device_admin,'get_patrol_repository',lambda:repository)
    monkeypatch.setattr(devices,'get_patrol_repository',lambda:repository)
    return repository
