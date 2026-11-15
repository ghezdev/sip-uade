import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest

from fall_detection import (
    DetectorConfig, DetectorState as State, EventType as Event,
    FallDetector, Measurement, TrackingStatus as Tracking,
)


def sample(t, y=0.4, aspect=0.4, **changes):
    return replace(Measurement(t, True, y, 0.4, aspect, 0.9), **changes)


def kinds(result):
    return [event.type for event in result.events]


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.config = DetectorConfig(
            floor_confirm_seconds=1.0, recovery_seconds=0.5,
        )
        self.detector = FallDetector(self.config)

    def start_fall(self, detector=None, offset=0.0):
        detector = detector or self.detector
        for t in (0.0, 0.25, 0.5):
            detector.update(sample(offset + t))
        return detector.update(sample(offset + 0.75, y=0.8, aspect=1.2))

    def confirm_fall(self):
        self.start_fall()
        results = [self.detector.update(sample(t, y=0.8, aspect=1.2))
                   for t in (1.0, 1.25, 1.5, 1.75)]
        return results[-1]

    def test_initial_absence_and_single_person_detected(self):
        absent = self.detector.update(Measurement(0, False))
        self.assertEqual(absent.state, State.NO_PERSON)
        self.assertEqual(absent.tracking, Tracking.ABSENT)
        self.assertFalse(absent.events)
        detected = self.detector.update(sample(0.25))
        self.assertEqual(detected.state, State.STANDING)
        self.assertEqual(kinds(detected), [Event.PERSON_DETECTED])
        self.assertFalse(self.detector.update(sample(0.5)).events)

    def test_fall_requires_speed_descent_then_horizontal_posture(self):
        result = self.start_fall()
        self.assertEqual(result.state, State.ON_FLOOR)
        self.assertEqual(kinds(result), [Event.FALL_STARTED, Event.PERSON_ON_FLOOR])
        self.assertAlmostEqual(result.metrics.hip_descent, 1.0)
        self.assertAlmostEqual(result.metrics.fall_speed, 2.0)
        self.assertTrue(result.episode_id)
        self.assertTrue(all(e.episode_id == result.episode_id for e in result.events))

    def test_confirmation_at_deadline_once_per_episode(self):
        result = self.confirm_fall()
        self.assertEqual(kinds(result), [Event.FALL_CONFIRMED])
        self.assertEqual(result.metrics.floor_seconds, 1.0)
        self.assertEqual(result.events[0].floor_seconds, 1.0)
        for t in (2, 2.25, 2.5, 2.75, 3):
            later = self.detector.update(sample(t, y=0.8, aspect=1.2))
            self.assertFalse(later.events)
            self.assertEqual(later.episode_id, result.episode_id)

    def test_no_confirmation_before_deadline(self):
        self.start_fall()
        for t in (1.0, 1.25, 1.5):
            self.assertNotIn(Event.FALL_CONFIRMED,
                             kinds(self.detector.update(sample(t, 0.8, 1.2))))

    def test_horizontal_person_at_start_is_unknown_not_a_fall(self):
        for t in (0, 0.25, 0.5, 0.75, 1, 1.25):
            result = self.detector.update(sample(t, 0.8, 1.2))
            self.assertEqual(result.state, State.UNKNOWN)
            self.assertIsNone(result.episode_id)
            self.assertNotIn(Event.FALL_CONFIRMED, kinds(result))
        self.assertEqual(self.detector.update(sample(1.5)).state, State.STANDING)

    def test_slow_lying_down_uses_posture_route_without_rapid_fall_event(self):
        for i in range(25):
            t = i * 0.25
            result = self.detector.update(sample(t, 0.4 + min(t, 4) * 0.1,
                                                  1.2 if t >= 4 else 0.4))
            self.assertNotIn(Event.FALL_STARTED, kinds(result))
        self.assertIsNotNone(result.episode_id)
        self.assertEqual(result.criterion.value, 'posture_change')

    def test_fast_sitting_without_horizontal_posture_times_out(self):
        for t in (0, 0.25, 0.5):
            self.detector.update(sample(t))
        candidate = self.detector.update(sample(0.75, 0.8, 0.5))
        self.assertEqual(candidate.state, State.FALLING)
        for t in (1, 1.25, 1.5, 1.75, 2, 2.25, 2.5):
            result = self.detector.update(sample(t, 0.8, 0.5))
            self.assertNotIn(Event.PERSON_ON_FLOOR, kinds(result))
            self.assertNotIn(Event.FALL_CONFIRMED, kinds(result))
        self.assertIsNone(result.episode_id)

    def test_descent_alone_is_not_floor_evidence(self):
        result = self.start_fall(FallDetector(replace(self.config, lying_aspect_ratio=2)))
        self.assertEqual(result.state, State.FALLING)
        self.assertEqual(kinds(result), [Event.FALL_STARTED])

    def test_min_descent_is_required_even_when_speed_is_high(self):
        detector = FallDetector(replace(self.config, min_descent=2))
        self.assertIsNone(self.start_fall(detector).episode_id)

    def test_stable_recovery_and_rearm_allow_a_new_episode(self):
        first = self.confirm_fall()
        for t in (2, 2.25):
            self.assertNotIn(Event.PERSON_RECOVERED, kinds(self.detector.update(sample(t))))
        recovered = self.detector.update(sample(2.5))
        self.assertEqual(recovered.state, State.RECOVERED)
        self.assertEqual(kinds(recovered), [Event.PERSON_RECOVERED])
        self.assertIsNone(recovered.episode_id)
        self.assertEqual(recovered.events[0].episode_id, first.episode_id)
        self.detector.update(sample(2.75))
        rearmed = self.detector.update(sample(3))
        self.assertEqual(rearmed.state, State.STANDING)
        self.assertIsNone(rearmed.episode_id)
        second = self.start_fall(offset=3.25)
        self.assertNotEqual(first.episode_id, second.episode_id)
        for t in (4.25, 4.5, 4.75, 5):
            result = self.detector.update(sample(t, 0.8, 1.2))
        self.assertIn(Event.FALL_CONFIRMED, kinds(result))

    def test_narrow_posture_with_hip_still_low_is_not_recovery(self):
        self.confirm_fall()
        for t in (2, 2.25, 2.5, 2.75):
            result = self.detector.update(sample(t, 0.8, 0.4))
            self.assertEqual(result.state, State.RECOVERING)
            self.assertNotIn(Event.PERSON_RECOVERED, kinds(result))

    def test_brief_recovery_does_not_recover(self):
        self.confirm_fall()
        self.detector.update(sample(2))
        self.detector.update(sample(2.25))
        result = self.detector.update(sample(2.5, 0.8, 1.2))
        self.assertEqual(result.state, State.ON_FLOOR)
        self.assertNotIn(Event.PERSON_RECOVERED, kinds(result))

    def test_relapse_before_rearm_keeps_episode_and_deduplicates(self):
        self.detector = FallDetector(replace(self.config, recovery_seconds=1.0))
        original = self.confirm_fall()
        all_events = []
        for t, lying in ((2, False), (2.25, False), (2.5, False), (2.75, True),
                         (3, True), (3.25, True), (3.5, True), (3.75, True),
                         (4, False), (4.25, False), (4.5, False)):
            result = self.detector.update(sample(t, 0.8 if lying else 0.4,
                                                   1.2 if lying else 0.4))
            all_events.extend(kinds(result))
            self.assertEqual(result.episode_id, original.episode_id)
        self.assertEqual(all_events.count(Event.PERSON_RECOVERED), 0)
        self.assertNotIn(Event.FALL_STARTED, all_events)
        self.assertNotIn(Event.PERSON_ON_FLOOR, all_events)
        self.assertNotIn(Event.FALL_CONFIRMED, all_events)

    def test_invalid_measurements_are_explicit_and_never_enter_motion_history(self):
        cases = [dict(visibility=0.1), dict(visibility=2), dict(visibility=None),
                 dict(hip_y=float('nan')), dict(hip_y=float('inf')),
                 dict(hip_y=None), dict(torso_length=0), dict(torso_length=-1),
                 dict(aspect_ratio=0), dict(aspect_ratio=None),
                 dict(torso_length=True), dict(person_present='yes')]
        for changes in cases:
            with self.subTest(changes=changes):
                detector = FallDetector(self.config)
                detector.update(sample(0))
                result = detector.update(sample(0.25, **changes))
                self.assertEqual(result.tracking, Tracking.INVALID)
                self.assertIsNotNone(result.metrics.invalid_reason)
                self.assertIsNone(result.metrics.fall_speed)
                resumed = detector.update(sample(0.5, 0.8, 1.2))
                self.assertIsNone(resumed.metrics.fall_speed)
                self.assertNotIn(Event.FALL_STARTED, kinds(resumed))

    def test_short_dropout_preserves_state_but_restarts_floor_evidence(self):
        episode = self.start_fall().episode_id
        missing = self.detector.update(Measurement(1, False))
        self.assertEqual(missing.state, State.ON_FLOOR)
        self.assertEqual(missing.tracking, Tracking.ABSENT)
        self.assertFalse(missing.events)
        self.assertEqual(missing.metrics.floor_seconds, 0)
        for t in (1.25, 1.5, 1.75, 2):
            result = self.detector.update(sample(t, 0.8, 1.2))
            self.assertNotIn(Event.FALL_CONFIRMED, kinds(result))
            self.assertEqual(result.episode_id, episode)
        self.assertIn(Event.FALL_CONFIRMED,
                      kinds(self.detector.update(sample(2.25, 0.8, 1.2))))

    def test_tracking_loss_at_timeout_emits_once(self):
        self.detector.update(sample(0))
        self.detector.update(Measurement(0.5, False))
        lost = self.detector.update(Measurement(1, False))
        self.assertEqual(lost.state, State.NO_PERSON)
        self.assertEqual(lost.tracking, Tracking.LOST)
        self.assertEqual(kinds(lost), [Event.PERSON_LOST])
        self.assertFalse(self.detector.update(Measurement(1.5, False)).events)
        found = self.detector.update(sample(2))
        self.assertEqual(kinds(found), [Event.PERSON_DETECTED])
        self.assertIsNone(found.metrics.fall_speed)

    def test_valid_arrival_after_long_gap_reports_loss_and_reacquisition(self):
        self.detector.update(sample(0))
        result = self.detector.update(sample(2))
        self.assertEqual(kinds(result), [Event.PERSON_LOST, Event.PERSON_DETECTED])
        self.assertIsNone(result.metrics.fall_speed)

    def test_confirmed_episode_survives_long_loss_without_duplicate_confirmation(self):
        confirmed = self.confirm_fall()
        self.detector.update(Measurement(2, False))
        lost = self.detector.update(Measurement(3, False))
        self.assertEqual(lost.state, State.NO_PERSON)
        self.assertEqual(lost.episode_id, confirmed.episode_id)
        for t in (3.25, 3.5, 3.75, 4, 4.25, 4.5):
            result = self.detector.update(sample(t, 0.8, 1.2))
            self.assertNotIn(Event.FALL_CONFIRMED, kinds(result))
            self.assertNotIn(Event.PERSON_ON_FLOOR, kinds(result))
            self.assertEqual(result.episode_id, confirmed.episode_id)

    def test_long_loss_does_not_confirm_unobserved_floor_time(self):
        self.start_fall()
        self.detector.update(Measurement(1, False))
        self.detector.update(Measurement(2, False))
        resumed = self.detector.update(sample(10, 0.8, 1.2))
        self.assertNotIn(Event.FALL_CONFIRMED, kinds(resumed))
        self.assertEqual(resumed.metrics.floor_seconds, 0)

    def test_sample_gap_below_loss_timeout_still_breaks_continuity(self):
        self.start_fall()
        result = self.detector.update(sample(1.5, 0.8, 1.2))
        self.assertNotIn(Event.PERSON_LOST, kinds(result))
        self.assertEqual(result.metrics.floor_seconds, 0)
        self.assertIsNone(result.metrics.fall_speed)

    def test_expired_candidate_is_not_resurrected_after_loss(self):
        for t in (0, 0.25, 0.5):
            self.detector.update(sample(t))
        self.detector.update(sample(0.75, 0.8, 0.5))
        result = self.detector.update(sample(3, 0.8, 1.2))
        self.assertEqual(result.state, State.UNKNOWN)
        self.assertIsNone(result.episode_id)
        self.assertNotIn(Event.PERSON_ON_FLOOR, kinds(result))

    def test_invalid_input_interrupts_recovery_then_confirmation_rearms_immediately(self):
        self.confirm_fall()
        self.detector.update(sample(2))
        self.detector.update(sample(2.25, visibility=0))
        for t in (2.5, 2.75):
            self.assertNotIn(Event.PERSON_RECOVERED, kinds(self.detector.update(sample(t))))
        self.assertIn(Event.PERSON_RECOVERED, kinds(self.detector.update(sample(3))))
        self.detector.update(sample(3.25, visibility=0))
        self.assertEqual(self.detector.update(sample(3.5)).state, State.STANDING)
        self.assertEqual(self.detector.update(sample(3.75)).state, State.STANDING)
        self.assertEqual(self.detector.update(sample(4)).state, State.STANDING)

    def test_aspect_jitter_pauses_confirmation_without_erasing_accumulated_time(self):
        self.start_fall()
        self.detector.update(sample(1, 0.8, 1.2))
        self.detector.update(sample(1.25, 0.8, 0.9))
        for t in (1.5, 1.75, 2):
            result = self.detector.update(sample(t, 0.8, 1.2))
            self.assertFalse(result.events)
        self.assertEqual(kinds(self.detector.update(sample(2.25, 0.8, 1.2))),
                         [Event.FALL_CONFIRMED])

    def test_timestamps_rejected_before_mutating_state(self):
        self.detector.update(sample(1))
        for t in (1, 0.5, -1, float('nan'), float('inf'), True, '2'):
            with self.subTest(t=t), self.assertRaises(ValueError):
                self.detector.update(sample(t))
        result = self.detector.update(sample(1.25))
        self.assertEqual(result.state, State.STANDING)
        self.assertFalse(result.events)

    def test_configuration_changes_confirmation_time(self):
        detector = FallDetector(replace(self.config, floor_confirm_seconds=0.5))
        self.start_fall(detector)
        self.assertFalse(detector.update(sample(1, 0.8, 1.2)).events)
        self.assertEqual(kinds(detector.update(sample(1.25, 0.8, 1.2))),
                         [Event.FALL_CONFIRMED])

    def test_equivalent_trajectories_at_multiple_frame_rates(self):
        for fps in (5, 30, 120, 240):
            with self.subTest(fps=fps):
                detector = FallDetector(self.config)
                emitted = []
                for i in range(4 * fps + 1):
                    t = i / fps
                    y = 0.4 + 0.4 * min(max((t - 0.5) / 0.5, 0), 1)
                    result = detector.update(sample(t, y, 1.2 if t >= 1 else 0.4))
                    emitted.extend(result.events)
                for kind in (Event.FALL_STARTED, Event.PERSON_ON_FLOOR, Event.FALL_CONFIRMED):
                    self.assertEqual(sum(e.type == kind for e in emitted), 1)
                confirmed = next(e for e in emitted if e.type == Event.FALL_CONFIRMED)
                self.assertLessEqual(confirmed.timestamp, 2 + 1 / fps)

    def test_isotropic_scale_does_not_change_detection(self):
        for scale in (0.5, 1, 2):
            detector = FallDetector(self.config)
            for t in (0, 0.25, 0.5):
                detector.update(sample(t, 0.4 * scale, torso_length=0.4 * scale))
            result = detector.update(sample(0.75, 0.8 * scale, 1.2,
                                            torso_length=0.4 * scale))
            self.assertEqual(result.state, State.ON_FLOOR)
            self.assertAlmostEqual(result.metrics.fall_speed, 2)

    def test_reference_torso_is_used_instead_of_current_foreshortened_torso(self):
        for t in (0, 0.25, 0.5):
            self.detector.update(sample(t))
        result = self.detector.update(sample(0.75, 0.5, 1.2, torso_length=0.05))
        self.assertAlmostEqual(result.metrics.hip_descent, 0.25)
        self.assertIsNone(result.episode_id)

    def test_event_ids_are_unique_and_results_immutable(self):
        result = self.start_fall()
        self.assertEqual(len({e.event_id for e in result.events}), len(result.events))
        with self.assertRaises(FrozenInstanceError):
            result.state = State.STANDING
        with self.assertRaises(FrozenInstanceError):
            result.events[0].timestamp = 99

    def test_bending_without_enough_descent_does_not_start_fall(self):
        for t in (0, 0.25, 0.5):
            self.detector.update(sample(t))
        for t, y, aspect in ((0.75, 0.5, 1.1), (1, 0.5, 1.1),
                             (1.25, 0.4, 0.4), (1.5, 0.4, 0.4)):
            result = self.detector.update(sample(t, y, aspect))
            self.assertIsNone(result.episode_id)
            self.assertFalse(result.events)

    def test_low_visibility_eventually_loses_tracking(self):
        self.detector.update(sample(0))
        for t in (0.25, 0.5, 0.75):
            result = self.detector.update(sample(t, visibility=0.1))
            self.assertEqual(result.tracking, Tracking.INVALID)
        lost = self.detector.update(sample(1, visibility=0.1))
        self.assertEqual(lost.tracking, Tracking.LOST)
        self.assertEqual(lost.metrics.invalid_reason, 'low_visibility')
        self.assertEqual(kinds(lost), [Event.PERSON_LOST])

    def test_same_gap_and_tracking_timeout_breaks_continuity_at_boundary(self):
        detector = FallDetector(replace(self.config, tracking_timeout_seconds=0.5))
        self.start_fall(detector)
        result = detector.update(sample(1.25, 0.8, 1.2))
        self.assertEqual(result.metrics.floor_seconds, 0)
        self.assertEqual(kinds(result), [Event.PERSON_LOST, Event.PERSON_DETECTED])

    def test_default_confirmation_requires_fifteen_seconds(self):
        detector = FallDetector()
        self.start_fall(detector)
        for i in range(4, 63):
            result = detector.update(sample(i * 0.25, 0.8, 1.2))
            self.assertNotIn(Event.FALL_CONFIRMED, kinds(result))
        self.assertEqual(kinds(detector.update(sample(15.75, 0.8, 1.2))),
                         [Event.FALL_CONFIRMED])

    def test_motion_uses_actual_elapsed_time_with_irregular_sampling(self):
        for t in (0, 0.13, 0.39, 0.52):
            self.detector.update(sample(t))
        result = self.detector.update(sample(0.9, 0.8, 1.2))
        self.assertAlmostEqual(result.metrics.hip_descent, 1)
        self.assertAlmostEqual(result.metrics.fall_speed, 1 / (0.9 - 0.39))
        self.assertEqual(result.state, State.ON_FLOOR)


class ContractTests(unittest.TestCase):
    def test_invalid_configuration_is_rejected(self):
        for changes in (dict(floor_confirm_seconds=0), dict(recovery_seconds=-1),
                        dict(fall_speed_threshold=float('nan')), dict(min_descent=True),
                        dict(min_visibility=2), dict(upright_aspect_ratio=1),
                        dict(max_sample_gap_seconds=2), dict(lying_torso_angle=100),
                        dict(upright_torso_angle=70), dict(posture_angle_change=50),
                        dict(posture_window_seconds=.1), dict(posture_hold_seconds=6)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                DetectorConfig(**changes)

    def test_engine_package_has_no_external_or_alert_imports(self):
        allowed = {'__future__', 'collections', 'dataclasses', 'enum', 'math', 'typing', 'uuid'}
        for path in (Path(__file__).resolve().parents[1] / 'fall_detection').glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split('.')[0], allowed)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module.split('.')[0], allowed)


if __name__ == '__main__':
    unittest.main()
