import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
from datetime import timedelta
from flask import Flask
from app.extensions import db, socketio
from app.users.models import User
from app.drivers.models import Driver
from app.trips.models import Trip, RideOffer, TripStageEvent
from app.trips.services import build_dispatch_plan, activate_due_offers, accept_trip_offer, decline_trip_offer, utcnow
from app.drivers.stream import build_driver_request_queue
from app.trips.timing import trip_timing
from app.admin.services import delete_driver, dashboard_counts, all_drivers, delete_trip
from app.admin import live
from app.admin.routes import bp as admin_bp
from app.admin.platform_map import platform_snapshot
from app.drivers.services import haversine_miles
from app.admin.settings import save_dispatch_settings, get_dispatch_settings, distance_fraction
from unittest.mock import patch
from app.drivers.routes import bp

class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SECRET_KEY='test', DEMO_MODE=True)
        db.init_app(self.app); socketio.init_app(self.app)
        self.app.register_blueprint(bp, url_prefix='/drivers')
        self.app.register_blueprint(admin_bp, url_prefix='/admin')
        self.ctx = self.app.app_context(); self.ctx.push(); db.create_all()
        self.drivers = [Driver(display_name=f'Driver {i}', email=f'd{i}@test.local', verification_status='APPROVED',
            is_online=True, is_available=True, current_latitude=33.72 + i * .001, current_longitude=-116.22)
            for i in range(7)]
        self.drivers[-1].current_latitude=35
        db.session.add_all(self.drivers); db.session.commit()
        save_dispatch_settings({"radius_miles":5,"expansion_seconds":0,"response_seconds":20})
    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()
    def trip(self):
        t=Trip(passenger_name='Test', status='REQUESTED', pickup_latitude=33.72, pickup_longitude=-116.22,
            destination_latitude=33.73, destination_longitude=-116.23, estimated_distance_meters=1000,
            estimated_duration_seconds=120, estimated_fare=7, route_provider='test',
            route_geometry_json='{"type":"LineString","coordinates":[[-116.22,33.72],[-116.23,33.73]]}')
        db.session.add(t); db.session.commit(); return t
    def test_zero_expansion_radius_and_expiry(self):
        t=self.trip(); offers=build_dispatch_plan(t.id)
        self.assertEqual(len(offers),6)
        self.assertTrue(all(o.status=='OFFERED' for o in offers))
        self.assertEqual(len({o.eligible_at for o in offers}),1)
        self.assertEqual(build_driver_request_queue(self.drivers[-1].id),[])
        for o in offers: o.expires_at=utcnow()-timedelta(seconds=1)
        db.session.commit()
        with self.assertRaisesRegex(ValueError,'expired'): accept_trip_offer(t.id,offers[0].driver_id)
        db.session.rollback()
        self.assertEqual(len(activate_due_offers(t.id)),6)
        self.assertEqual(t.status,'REQUESTED')
        self.assertTrue(all(o.status=='EXPIRED' for o in offers))
    def test_competition_and_history(self):
        t=self.trip(); offers=build_dispatch_plan(t.id)
        decline_trip_offer(t.id,offers[0].driver_id)
        self.assertEqual(offers[1].status,'OFFERED')
        accept_trip_offer(t.id,offers[1].driver_id)
        with self.assertRaises(ValueError): accept_trip_offer(t.id,offers[2].driver_id)
        db.session.rollback()
        t.status='DRIVER_EN_ROUTE'; db.session.commit()
        stages=trip_timing(t)['stages']
        self.assertEqual(stages[-1]['status'],'DRIVER_EN_ROUTE')
        self.assertTrue(all(e['entered_at'].endswith('+00:00') for e in stages))
        client=socketio.test_client(self.app); client.emit('register_admin')
        packets=client.get_received()
        self.assertTrue(any(p['name']=='admin_snapshot' for p in packets))
        live.publish_admin_trip(t.id)
        self.assertTrue(any(p['name']=='admin_trip_update' for p in client.get_received()))
        client.disconnect()
        delete_trip(t.id); self.assertEqual(TripStageEvent.query.count(),0)
    def test_linear_distance_schedule_and_persisted_settings(self):
        save_dispatch_settings({"radius_miles":5,"expansion_seconds":20,"response_seconds":20})
        t=self.trip()
        ranked=[{"driver":self.drivers[i],"distance_miles":distance} for i,distance in enumerate([1,2,5,6])]
        with patch('app.trips.services.available_drivers_ranked', return_value=ranked):
            offers=build_dispatch_plan(t.id)
        self.assertEqual([o.distance_fraction for o in offers],[0,.25,1])
        self.assertEqual([o.status for o in offers],['OFFERED','WAITING','WAITING'])
        delays=[(o.eligible_at-offers[0].eligible_at).total_seconds() for o in offers]
        self.assertEqual(delays,[0,5,20])
        self.assertEqual(build_driver_request_queue(offers[1].driver_id),[])
        with self.assertRaises(ValueError): accept_trip_offer(t.id,offers[1].driver_id)
        db.session.rollback()
        start=offers[0].eligible_at
        with patch('app.trips.services.utcnow', return_value=start+timedelta(seconds=4)):
            self.assertEqual(activate_due_offers(t.id),[])
        with patch('app.trips.services.utcnow', return_value=start+timedelta(seconds=5)):
            self.assertEqual(len(activate_due_offers(t.id)),1)
        self.assertEqual(offers[1].status,'OFFERED')
        self.assertEqual(len(build_driver_request_queue(offers[1].driver_id)),1)
        with patch('app.trips.services.utcnow', return_value=start+timedelta(seconds=6)):
            decline_trip_offer(t.id,offers[1].driver_id)
        self.assertEqual(offers[2].status,'WAITING')
        save_dispatch_settings({"radius_miles":3,"expansion_seconds":60,"response_seconds":30})
        db.session.expire_all()
        self.assertEqual(get_dispatch_settings()['expansion_seconds'],60)
        self.assertEqual((offers[2].eligible_at-start).total_seconds(),20)
        with patch('app.trips.services.utcnow', return_value=start+timedelta(seconds=20)):
            activate_due_offers(t.id)
        self.assertEqual(offers[2].status,'OFFERED')
        self.assertEqual((offers[2].expires_at-offers[2].offered_at).total_seconds(),20)
        self.assertEqual(distance_fraction(2,2,2),0)
        self.assertEqual(distance_fraction(1,1,1),0)
        with self.assertRaises(ValueError): save_dispatch_settings({"radius_miles":float('nan'),"expansion_seconds":20,"response_seconds":20})

    def test_offline_waiting_driver_never_activated(self):
        save_dispatch_settings({"radius_miles":5,"expansion_seconds":20,"response_seconds":20})
        t=self.trip(); offers=build_dispatch_plan(t.id)
        waiting=offers[-1]
        driver=db.session.get(Driver,waiting.driver_id);driver.is_online=False;db.session.commit()
        with patch('app.trips.services.utcnow', return_value=waiting.eligible_at+timedelta(seconds=1)):
            activate_due_offers(t.id)
        self.assertEqual(waiting.status,'CLOSED')

    def test_admin_map_and_randomization(self):
        driver=self.drivers[0]
        driver.is_online=False;driver.is_available=False
        passenger=User(email='p@test.local',display_name='Rider',role='PASSENGER')
        admin=User(email='a@test.local',display_name='Admin',role='ADMIN')
        driver_account=User(email=driver.email,display_name=driver.display_name,role='DRIVER')
        db.session.add_all([passenger,admin,driver_account]);db.session.commit()
        t=self.trip();t.passenger_id=passenger.id;t.driver_id=self.drivers[1].id;t.status='DRIVER_EN_ROUTE';db.session.commit()
        before=(self.drivers[1].current_latitude,self.drivers[1].current_longitude)
        socket_client=socketio.test_client(self.app);socket_client.emit('register_admin')
        self.assertTrue(any(event['name']=='admin_platform_map' for event in socket_client.get_received()))
        client=self.app.test_client();url='/admin/demo/randomize-drivers'
        payload={'latitude':33.72,'longitude':-116.22,'radius_miles':3}
        response=client.post(url,json=payload)
        self.assertEqual(response.status_code,200)
        self.assertIn(self.drivers[1].id,response.json['skipped_driver_ids'])
        self.assertEqual(before,(self.drivers[1].current_latitude,self.drivers[1].current_longitude))
        self.assertFalse(driver.is_online);self.assertFalse(driver.is_available)
        for d in self.drivers:
            if d.id in response.json['updated_driver_ids']:
                self.assertLessEqual(haversine_miles(33.72,-116.22,d.current_latitude,d.current_longitude),3.000001)
        self.assertTrue(any(event['name']=='admin_platform_map' for event in socket_client.get_received()))
        people=platform_snapshot()['people']
        self.assertEqual(len(people),len(self.drivers)+2)
        rider=next(p for p in people if p['key']==f'user:{passenger.id}')
        self.assertEqual(rider['latitude'],t.pickup_latitude)
        self.assertIn('not live',rider['location_kind'])
        self.assertIsNone(next(p for p in people if p['role']=='ADMIN')['latitude'])
        self.assertEqual(client.post(url,json={**payload,'radius_miles':-1}).status_code,400)
        self.app.config['DEMO_MODE']=False
        self.assertEqual(client.post(url,json=payload).status_code,403)
        socket_client.disconnect()

    def test_offline_persists_and_closes_offers(self):
        t=self.trip(); offers=build_dispatch_plan(t.id); driver_id=offers[0].driver_id
        c=self.app.test_client(); url=f'/drivers/{driver_id}/availability'
        self.assertEqual(c.post(url,json={'is_online': 'false'}).status_code,400)
        result=c.post(url,json={'is_online':False})
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.json['is_online'])
        self.assertFalse(result.json['is_available'])
        self.assertEqual(build_driver_request_queue(driver_id),[])
        self.assertEqual(offers[0].status,'CLOSED')
        self.assertEqual(offers[1].status,'OFFERED')
        db.session.expire_all()
        self.assertFalse(c.get(f'/drivers/{driver_id}').json['is_online'])
        with self.assertRaises(ValueError): accept_trip_offer(t.id,driver_id)
        db.session.rollback()
        newer=self.trip()
        self.assertNotIn(driver_id,[o.driver_id for o in build_dispatch_plan(newer.id)])
        self.assertTrue(c.post(url,json={'is_online':True}).json['is_available'])
        self.assertEqual(offers[0].status,'CLOSED')

    def test_offline_preserves_accepted_trip(self):
        t=self.trip(); offers=build_dispatch_plan(t.id); driver_id=offers[0].driver_id
        accept_trip_offer(t.id,driver_id)
        c=self.app.test_client(); url=f'/drivers/{driver_id}/availability'
        self.assertEqual(c.post(url,json={'is_online':False}).status_code,200)
        self.assertEqual(t.status,'DRIVER_ASSIGNED')
        self.assertEqual(t.driver_id,driver_id)
        self.assertFalse(c.post(url,json={'is_online':True}).json['is_available'])
        driver=db.session.get(Driver,driver_id); driver.verification_status='PENDING';db.session.commit()
        self.assertEqual(c.post(url,json={'is_online':True}).status_code,403)

    def test_deleted_profile_and_map(self):
        d=self.drivers[0]
        db.session.add(User(email=d.email,display_name=d.display_name,role='DRIVER')); db.session.commit()
        driver_id=d.id; delete_driver(driver_id); dashboard_counts(); all_drivers()
        self.assertIsNone(db.session.get(Driver,driver_id))
        c=self.app.test_client(); target=self.drivers[1].id
        url=f'/drivers/{target}/demo-location'
        self.assertEqual(c.post(url,json={'latitude':33.71,'longitude':-116.2}).status_code,200)
        self.assertAlmostEqual(db.session.get(Driver,target).current_latitude,33.71)
        self.assertEqual(c.post(url,json={'latitude':100,'longitude':0}).status_code,400)
        self.app.config['DEMO_MODE']=False
        self.assertEqual(c.post(url,json={'latitude':0,'longitude':0}).status_code,403)
        self.app.config['DEMO_MODE']=True
        t=self.trip();t.driver_id=target;t.status='DRIVER_EN_ROUTE';db.session.commit()
        self.assertEqual(c.post(url,json={'latitude':0,'longitude':0}).status_code,409)

if __name__=='__main__': unittest.main()
