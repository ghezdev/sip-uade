"""Multi-route detection and episode continuity across failed recovery attempts."""

from dataclasses import replace
from math import cos, radians, sin
import unittest

from fall_detection import (
    DetectionCriterion as Criterion, DetectorConfig, DetectorState as State,
    EventType as Event, FallDetector, Measurement, TrackingStatus as Tracking,
)
from adapters.opencv_preview import FallingIndicator


def body(t, hip=.4, aspect=.4, angle=0, **changes):
    return replace(Measurement(t, True, hip, .4, aspect, .9,
                               hip - .4 * cos(radians(angle)), angle), **changes)


class RedesignTests(unittest.TestCase):
    def setUp(self):
        self.config = DetectorConfig(floor_confirm_seconds=3, recovery_seconds=5,
                                     posture_hold_seconds=.5, floor_persistence_seconds=2)
        self.detector = FallDetector(self.config)
        self.results = []

    def send(self, t, hip=.4, aspect=.4, angle=0, **changes):
        result = self.detector.update(body(t, hip, aspect, angle, **changes))
        self.results.append(result)
        return result

    def floor(self, t):
        return self.send(t, .8, 1.2, 80)

    def start(self, seated=False):
        for t in (0, .25, .5):
            self.send(t, .6 if seated else .4, .9 if seated else .4)
        return self.floor(.75)

    def types(self):
        return [e.type for result in self.results for e in result.events]

    def test_fast_fall_keeps_both_events_in_one_frame(self):
        result = self.start()
        self.assertEqual(result.state, State.ON_FLOOR)
        self.assertEqual(result.criterion, Criterion.RAPID_DESCENT)
        self.assertEqual([e.type for e in result.events], [Event.FALL_STARTED, Event.PERSON_ON_FLOOR])

    def test_fast_fall_exposes_falling_before_horizontal_posture(self):
        for t in (0, .25, .5):
            self.send(t)
        result = self.send(.75, .8, .5, 20)
        self.assertEqual(result.state, State.FALLING)
        self.assertEqual(self.floor(1).state, State.ON_FLOOR)

    def test_fast_route_retains_aspect_evidence_when_torso_is_foreshortened(self):
        for t in (0, .25, .5): self.send(t)
        result = self.send(.75, .8, 1.2, 20)
        self.assertEqual(result.state, State.ON_FLOOR)
        self.assertEqual(result.criterion, Criterion.RAPID_DESCENT)
        self.assertEqual(self.send(1, .8, 1.2, 20).metrics.floor_seconds, .25)

    def test_wide_seated_body_without_motion_does_not_trigger_persistence(self):
        for i in range(40):
            result = self.send(i * .25, .6, 1.2, 0)
            self.assertIsNone(result.episode_id)
        self.assertNotIn(Event.FALL_CONFIRMED, self.types())

    def test_slow_fall_uses_posture_without_speed_threshold(self):
        for i in range(13):
            t = i * .25
            fraction = min(t / 2, 1)
            self.send(t, .4 + .3 * fraction, .4 + .8 * fraction, 80 * fraction)
        result = self.results[-1]
        self.assertEqual(result.state, State.ON_FLOOR)
        self.assertEqual(result.criterion, Criterion.POSTURE_CHANGE)
        self.assertNotIn(Event.FALL_STARTED, self.types())
        self.assertIn(Event.FALL_SUSPECTED, self.types())
        speeds = [r.metrics.fall_speed for r in self.results if r.metrics.fall_speed is not None]
        self.assertLess(max(speeds), self.config.fall_speed_threshold)

    def test_seated_person_can_start_posture_episode_with_little_hip_movement(self):
        for t in (0, .25, .5):
            result = self.send(t, .6, .9, 0)
            self.assertEqual(result.state, State.UNKNOWN)
        for t in (.75, 1, 1.25):
            result = self.send(t, .65, 1.2, 80)
        self.assertEqual(result.state, State.ON_FLOOR)
        self.assertEqual(result.criterion, Criterion.POSTURE_CHANGE)
        self.assertNotIn(Event.FALL_STARTED, self.types())

    def test_rotation_without_any_hip_descent_is_detected(self):
        for t in (0, .25, .5):
            self.send(t)
        for t in (.75, 1, 1.25):
            result = self.send(t, .4, .9, 80)
        self.assertEqual(result.criterion, Criterion.POSTURE_CHANGE)
        self.assertEqual(result.state, State.ON_FLOOR)

    def test_initial_horizontal_posture_uses_persistence_not_invented_fall_motion(self):
        for i in range(13):
            result = self.floor(i * .25)
            if i < 8:
                self.assertIsNone(result.episode_id)
        self.assertEqual(result.criterion, Criterion.PERSISTENT_POSTURE)
        self.assertEqual(result.metrics.floor_seconds, 3)
        self.assertEqual(self.types().count(Event.FALL_CONFIRMED), 1)
        self.assertNotIn(Event.FALL_STARTED, self.types())

    def test_failed_attempt_preserves_episode_and_accumulation(self):
        episode = self.start().episode_id
        self.floor(1)
        before = self.floor(1.25).metrics.floor_seconds
        for t in (1.5, 1.75, 2):
            result = self.send(t)
            self.assertEqual(result.state, State.RECOVERING)
            self.assertEqual(result.episode_id, episode)
            self.assertEqual(result.metrics.floor_seconds, before)
        resumed = self.floor(2.25)
        self.assertEqual(resumed.episode_id, episode)
        self.assertEqual(resumed.metrics.floor_seconds, before)
        self.assertEqual(self.floor(2.5).metrics.floor_seconds, before + .25)
        self.assertNotIn(Event.PERSON_RECOVERED, self.types())

    def test_multiple_attempts_accumulate_toward_one_confirmation(self):
        episode = self.start().episode_id
        for t in (1, 1.25): self.floor(t)
        for t in (1.5, 1.75, 2): self.send(t)
        for t in (2.25, 2.5, 2.75): self.floor(t)
        for t in (3, 3.25, 3.5): self.send(t)
        for i in range(15, 24):
            result = self.floor(i * .25)
            self.assertEqual(result.episode_id, episode)
        self.assertEqual(result.metrics.floor_seconds, 3)
        self.assertEqual(self.types().count(Event.FALL_STARTED), 1)
        self.assertEqual(self.types().count(Event.PERSON_ON_FLOOR), 1)
        self.assertEqual(self.types().count(Event.FALL_CONFIRMED), 1)
        self.assertNotIn(Event.PERSON_RECOVERED, self.types())

    def test_recovery_requires_full_five_seconds_then_rearms(self):
        episode = self.start().episode_id
        self.floor(1)
        for i in range(5, 25):
            result = self.send(i * .25)
            self.assertEqual(result.state, State.RECOVERING)
            self.assertEqual(result.episode_id, episode)
        recovered = self.send(6.25)
        self.assertEqual(recovered.state, State.RECOVERED)
        self.assertIsNone(recovered.episode_id)
        self.assertEqual(recovered.events[0].type, Event.PERSON_RECOVERED)
        self.assertEqual(recovered.events[0].episode_id, episode)
        new_fall = self.floor(6.5)
        self.assertIsNotNone(new_fall.episode_id)
        self.assertNotEqual(new_fall.episode_id, episode)
        self.assertEqual(self.types().count(Event.FALL_STARTED), 2)

    def test_confirmed_episode_stays_confirmed_during_failed_recovery(self):
        episode = self.start().episode_id
        for i in range(4, 16): self.floor(i * .25)
        for t in (4, 4.25, 4.5): self.send(t)
        for i in range(19, 40):
            result = self.floor(i * .25)
            self.assertEqual(result.episode_id, episode)
        self.assertEqual(self.types().count(Event.FALL_CONFIRMED), 1)

    def test_low_upright_hip_is_only_provisional_not_confirmed_recovery(self):
        self.start()
        for i in range(4, 32):
            result = self.send(i * .25, .8, .5, 0)
            self.assertEqual(result.state, State.RECOVERING)
            self.assertEqual(result.metrics.recovery_seconds, 0)
        self.assertNotIn(Event.PERSON_RECOVERED, self.types())

    def test_recovery_can_finish_seated_at_pre_fall_height(self):
        for t in (0, .25, .5): self.send(t, .6, .9)
        for t in (.75, 1, 1.25): self.floor(t)
        for i in range(6, 27):
            result = self.send(i * .25, .6, .9, 0)
        self.assertEqual(result.state, State.RECOVERED)
        self.assertIn(Event.PERSON_RECOVERED, self.types())

    def test_fast_fall_from_chair_can_use_motion_route(self):
        for t in (0, .25, .5): self.send(t, .6, .9)
        result = self.send(.75, 1.0, 1.2, 80)
        self.assertEqual(result.criterion, Criterion.RAPID_DESCENT)
        self.assertEqual(result.state, State.ON_FLOOR)

    def test_tracking_loss_preserves_floor_time_and_interrupts_stable_recovery(self):
        episode = self.start().episode_id
        self.floor(1)
        self.floor(1.25)
        self.send(1.5)
        for t in (1.75, 2, 2.25, 2.5, 2.75):
            result = self.detector.update(Measurement(t, False))
            self.assertEqual(result.episode_id, episode)
            self.assertEqual(result.metrics.floor_seconds, .5)
            self.assertEqual(result.metrics.recovery_seconds, 0)
        self.assertEqual(result.tracking, Tracking.LOST)
        self.assertEqual(self.floor(3).episode_id, episode)
        self.assertEqual(self.floor(3.25).metrics.floor_seconds, .75)

    def test_unobserved_gap_is_not_credited_as_floor_or_recovery(self):
        self.start()
        self.floor(1)
        result = self.floor(5)
        self.assertEqual(result.metrics.floor_seconds, .25)
        self.send(5.25)
        result = self.send(12)
        self.assertEqual(result.state, State.RECOVERING)
        self.assertEqual(result.metrics.recovery_seconds, 0)

    def test_sitting_and_walking_never_confirm_floor(self):
        for i in range(65):
            t = i * .25
            hip = .4 + (.25 if t >= 1 else 0) + .02 * sin(t)
            result = self.send(t, hip, .9 if t >= 1 else .4, 0)
            self.assertNotEqual(result.state, State.ON_FLOOR)
        self.assertNotIn(Event.FALL_CONFIRMED, self.types())

    def test_bending_and_brief_horizontal_posture_do_not_confirm(self):
        for t in (0, .25, .5): self.send(t)
        self.send(.75, .45, .8, 80)
        for i in range(4, 40): self.send(i * .25)
        self.assertNotIn(Event.FALL_CONFIRMED, self.types())
        self.assertNotIn(Event.PERSON_ON_FLOOR, self.types())

    def test_short_voluntary_lie_then_stable_recovery_does_not_confirm(self):
        for t in (0, .25, .5): self.send(t)
        for i in range(3, 9): self.send(i * .25, .55, 1.2, 80)
        for i in range(9, 30): result = self.send(i * .25)
        self.assertEqual(result.state, State.RECOVERED)
        self.assertNotIn(Event.FALL_CONFIRMED, self.types())

    def test_long_voluntary_lying_remains_an_explicit_geometric_ambiguity(self):
        # Identical measured posture cannot reveal intent; report a possible event.
        for i in range(13): self.floor(i * .25)
        self.assertIn(Event.FALL_CONFIRMED, self.types())
        self.assertEqual(self.results[-1].criterion, Criterion.PERSISTENT_POSTURE)

    def test_optional_geometry_validation(self):
        for changes in ({'torso_angle': 91}, {'torso_angle': float('nan')},
                        {'shoulder_y': float('inf')}):
            with self.subTest(changes=changes):
                result = FallDetector().update(body(0, **changes))
                self.assertEqual(result.tracking, Tracking.INVALID)

    def test_falling_indicator_remembers_event_without_modifying_result(self):
        result = self.start()
        indicator = FallingIndicator(hold_seconds=2)
        self.assertIn('FALLING', indicator.observe(result, 10))
        later = self.floor(1)
        self.assertIn('FALLING', indicator.observe(later, 11))
        self.assertIsNone(indicator.observe(later, 12))
        self.assertEqual(result.state, State.ON_FLOOR)
        # Redisplaying the same event cannot extend the presentation deadline.
        self.assertIsNone(indicator.observe(result, 13))


if __name__ == '__main__':
    unittest.main()
