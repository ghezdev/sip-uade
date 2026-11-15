import unittest

from alerts import AlertState, AlertWorkflow
from fall_detection import DetectorConfig, DetectorEvent, EventType as Event, FallDetector
from tests.test_detector_redesign import body


def event(kind, t, episode='one'):
    return DetectorEvent(f'{episode}:{kind.value}:{t}', kind, t, episode)


class AlertTests(unittest.TestCase):
    def test_confirm_once_duplicate_and_loss_do_not_reset_deadline(self):
        workflow = AlertWorkflow(3)
        confirmed = event(Event.FALL_CONFIRMED, 1)
        self.assertEqual(workflow.update([confirmed], 1).deadline, 4)
        self.assertEqual(workflow.update([confirmed], 2).deadline, 4)
        self.assertEqual(workflow.update([event(Event.PERSON_LOST, 3)], 3).deadline, 4)
        self.assertEqual(workflow.update([], 4).state, AlertState.READY)
        self.assertEqual(workflow.update([confirmed], 5).state, AlertState.READY)

    def test_confirmed_recovery_cancels_at_deadline_and_prevents_replay(self):
        workflow = AlertWorkflow(3)
        confirmed = event(Event.FALL_CONFIRMED, 1)
        workflow.update([confirmed], 1)
        self.assertEqual(workflow.update([event(Event.PERSON_RECOVERED, 4)], 4).state,
                         AlertState.CANCELLED)
        self.assertEqual(workflow.update([confirmed], 5).state, AlertState.CANCELLED)
        new = workflow.update([event(Event.FALL_CONFIRMED, 6, 'two')], 6)
        self.assertEqual(new.state, AlertState.COUNTDOWN)
        self.assertEqual(new.deadline, 9)

    def test_real_detector_failed_recovery_keeps_countdown_success_cancels(self):
        detector = FallDetector(DetectorConfig(floor_confirm_seconds=1, recovery_seconds=5))
        workflow = AlertWorkflow(10)
        episode = None
        deadline = None
        for i in range(48):
            t = i * .25
            lying = .75 <= t < 2 or 2.75 <= t < 4
            result = detector.update(body(t, .8 if lying else .4, 1.2 if lying else .4,
                                          80 if lying else 0))
            status = workflow.update(result.events, t)
            if result.episode_id:
                episode = episode or result.episode_id
                self.assertEqual(result.episode_id, episode)
            if status.state == AlertState.COUNTDOWN:
                deadline = status.deadline if deadline is None else deadline
                self.assertEqual(status.deadline, deadline)
            if 2 <= t < 2.75:
                self.assertEqual(status.state, AlertState.COUNTDOWN)
            if t >= 9:
                self.assertEqual(status.state, AlertState.CANCELLED)
        self.assertIsNotNone(deadline)

    def test_timer_expires_even_during_provisional_recovery(self):
        detector = FallDetector(DetectorConfig(floor_confirm_seconds=1, recovery_seconds=5))
        workflow = AlertWorkflow(1)
        for i in range(13):
            t = i * .25
            lying = .75 <= t < 2
            result = detector.update(body(t, .8 if lying else .4, 1.2 if lying else .4,
                                          80 if lying else 0))
            status = workflow.update(result.events, t)
        self.assertEqual(status.state, AlertState.READY)

    def test_bad_clock_is_rejected_without_mutation(self):
        workflow = AlertWorkflow()
        workflow.update([], 1)
        for value in (0, float('nan'), True):
            with self.assertRaises(ValueError): workflow.update([], value)
        self.assertEqual(workflow.update([], 2).state, AlertState.IDLE)


if __name__ == '__main__':
    unittest.main()
