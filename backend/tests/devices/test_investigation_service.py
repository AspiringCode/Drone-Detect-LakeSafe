from types import SimpleNamespace
from app.models import Drone, DroneStatus, LatLon
from app.devices.investigations import select_second_drone


def test_nearest_fresh_patrolling_drone_only_and_never_detector():
    origin = LatLon(47.6, -122.1)
    drones = [Drone('first', origin, 1, DroneStatus.PATROLLING, None, source='real'),
              Drone('second', LatLon(47.601, -122.1), 1, DroneStatus.PATROLLING, None, source='real'),
              Drone('idle', origin, 1, DroneStatus.IDLE, None, source='real'),
              Drone('low', origin, .1, DroneStatus.PATROLLING, None, source='real')]
    assert select_second_drone('first', origin, drones) == 'second'
    assert select_second_drone('second', origin, drones[:1]) == 'first'
    assert select_second_drone('first', origin, []) is None
