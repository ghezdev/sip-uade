"""Adapter contracts with doubles: no camera, model or third-party imports needed."""

from dataclasses import replace
import io
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

from adapters.camera import CaptureError, OpenCVSource
from adapters.mediapipe_pose import (
    Landmark, MediaPipePose, PoseError, landmarks_to_measurement,
)
from adapters.opencv_preview import OpenCVPreview, diagnostic_lines
from fall_detection import FallDetector, Measurement, TrackingStatus
import runner


def body():
    # Eight distinct in-frame points; remaining landmarks have low visibility.
    points = [Landmark(0.5, 0.5, 0.0) for _ in range(33)]
    for i, x, y in ((0, .5, .1), (11, .4, .3), (12, .6, .3),
                    (23, .45, .6), (24, .55, .6), (25, .45, .75),
                    (27, .45, .9), (28, .55, .9)):
        points[i] = Landmark(x, y, .9)
    return points


class GeometryTests(unittest.TestCase):
    def convert(self, points, width=1280, height=720):
        return landmarks_to_measurement(points, 3.5, width, height, .5)

    def test_absent_person_keeps_timestamp(self):
        observation = self.convert([])
        self.assertFalse(observation.measurement.person_present)
        self.assertEqual(observation.measurement.timestamp, 3.5)
        result = FallDetector().update(observation.measurement)
        self.assertEqual(result.tracking, TrackingStatus.ABSENT)

    def test_isotropic_geometry_and_reference_contract(self):
        m = self.convert(body()).measurement
        self.assertEqual(m.timestamp, 3.5)
        self.assertAlmostEqual(m.hip_y, .6)
        self.assertAlmostEqual(m.torso_length, .3)
        self.assertAlmostEqual(m.aspect_ratio, .2 * (1280 / 720) / .8)
        self.assertAlmostEqual(m.shoulder_y, .3)
        self.assertAlmostEqual(m.torso_angle, 0)
        self.assertEqual(FallDetector().update(m).tracking, TrackingStatus.VALID)

    def test_resolution_change_with_same_aspect_does_not_change_measurements(self):
        self.assertEqual(self.convert(body(), 1280, 720).measurement,
                         self.convert(body(), 640, 360).measurement)

    def test_non_square_frame_corrects_horizontal_torso_distance(self):
        points = body()
        points[23] = Landmark(.65, .6, .9)
        points[24] = Landmark(.75, .6, .9)
        m = self.convert(points, 1440, 720).measurement
        self.assertAlmostEqual(m.torso_length, (.4 ** 2 + .3 ** 2) ** .5)
        from math import atan2, degrees
        self.assertAlmostEqual(m.torso_angle, degrees(atan2(.4, .3)))

    def test_low_key_visibility_is_explicit_to_engine(self):
        points = body()
        points[23] = replace(points[23], visibility=.1)
        observation = self.convert(points)
        result = FallDetector().update(observation.measurement)
        self.assertEqual(result.tracking, TrackingStatus.INVALID)
        self.assertEqual(result.metrics.invalid_reason, 'low_visibility')

    def test_partial_body_missing_points_and_bad_geometry_are_invalid_not_absent(self):
        partial = body()
        partial[23] = replace(partial[23], x=1.2)
        malformed = body()
        malformed[11] = replace(malformed[11], y=float('nan'))
        missing_coordinate = body()
        missing_coordinate[23] = replace(missing_coordinate[23], x=None)
        insufficient = body()
        insufficient[0] = replace(insufficient[0], visibility=0)
        degenerate = [Landmark(.5, .5, .9)] * 33
        for points in (partial, malformed, missing_coordinate, insufficient, degenerate, body()[:20]):
            with self.subTest(points=points):
                observation = self.convert(points)
                self.assertTrue(observation.measurement.person_present)
                self.assertTrue(observation.diagnostic)
                self.assertEqual(FallDetector().update(observation.measurement).tracking,
                                 TrackingStatus.INVALID)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.video = Path(self.temp.name) / 'video.avi'
        self.video.touch()
        self.frame = SimpleNamespace(size=100, shape=(720, 1280, 3))

    def cv(self, frames=3, fps=25, positions=(0, 40, 80), opened=True):
        cap = Mock()
        cap.isOpened.return_value = opened
        cap.read.side_effect = [(True, self.frame)] * frames + [(False, None)]
        times = iter(positions)
        def get(prop):
            return next(times) if prop == 'time' else {'fps': fps, 'count': frames}[prop]
        cap.get.side_effect = get
        cv = SimpleNamespace(VideoCapture=Mock(return_value=cap), CAP_PROP_FPS='fps',
                             CAP_PROP_FRAME_COUNT='count', CAP_PROP_POS_MSEC='time')
        return cv, cap

    def test_video_uses_media_time_not_processing_clock_and_eof_is_normal(self):
        cv, cap = self.cv()
        with OpenCVSource(self.video, cv2_module=cv, clock=Mock(side_effect=AssertionError)) as source:
            frames = [source.read() for _ in range(3)]
            self.assertEqual([f.timestamp for f in frames], [0, .04, .08])
            self.assertEqual([f.index for f in frames], [0, 1, 2])
            self.assertIsNone(source.read())
        cap.release.assert_called_once()

    def test_live_camera_uses_monotonic_clock_and_failure_is_error(self):
        cv, cap = self.cv(frames=2)
        with OpenCVSource(1, cv2_module=cv, clock=Mock(side_effect=[10.0, 10.1])) as source:
            self.assertEqual(source.read().timestamp, 10)
            self.assertEqual(source.read().timestamp, 10.1)
            with self.assertRaises(CaptureError):
                source.read()
        cap.release.assert_called_once()
        cv.VideoCapture.assert_called_once_with(1)

    def test_missing_video_does_not_open_capture(self):
        cv, _ = self.cv()
        with self.assertRaises(CaptureError):
            with OpenCVSource(self.video.parent / 'missing.mp4', cv2_module=cv):
                pass
        cv.VideoCapture.assert_not_called()

    def test_open_failure_releases_capture(self):
        cv, cap = self.cv(opened=False)
        with self.assertRaises(CaptureError):
            with OpenCVSource(0, cv2_module=cv):
                pass
        cap.release.assert_called_once()

    def test_video_without_media_timestamps_uses_fps_and_warns(self):
        cv, _ = self.cv(positions=(0, 0, 0))
        with OpenCVSource(self.video, cv2_module=cv) as source:
            frames = [source.read() for _ in range(3)]
            self.assertEqual([f.timestamp for f in frames], [0, .04, .08])
            self.assertTrue(source.timing_warning)

    def test_override_fps_is_explicit_and_independent_of_metadata(self):
        cv, _ = self.cv(fps=0)
        with OpenCVSource(self.video, cv2_module=cv, video_fps=10) as source:
            self.assertEqual([source.read().timestamp for _ in range(3)], [0, .1, .2])

    def test_bad_media_time_and_fps_require_explicit_override(self):
        cv, _ = self.cv(fps=0, positions=(0, 0, 0))
        with OpenCVSource(self.video, cv2_module=cv) as source:
            source.read()
            with self.assertRaisesRegex(CaptureError, 'video-fps'):
                source.read()

    def test_premature_decode_failure_is_error(self):
        cv, cap = self.cv(frames=100)
        cap.read.side_effect = [(True, self.frame), (False, None)]
        with OpenCVSource(self.video, cv2_module=cv) as source:
            source.read()
            with self.assertRaisesRegex(CaptureError, 'antes del final'):
                source.read()

    def test_empty_video_is_not_successful_eof(self):
        cv, _ = self.cv(frames=0)
        with OpenCVSource(self.video, cv2_module=cv) as source:
            with self.assertRaisesRegex(CaptureError, 'vacio'):
                source.read()

    def test_non_increasing_live_clock_is_rejected(self):
        cv, _ = self.cv()
        with OpenCVSource(0, cv2_module=cv, clock=lambda: 1) as source:
            source.read()
            with self.assertRaises(CaptureError):
                source.read()


class PoseTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / 'model.task'
        self.model.touch()
        self.task = Mock()
        self.task.detect_for_video.return_value = SimpleNamespace(pose_landmarks=[body()])
        self.cv = SimpleNamespace(COLOR_BGR2RGB=42, cvtColor=Mock(return_value='rgb'))
        self.options = Mock(return_value='options')
        self.mp = SimpleNamespace(
            tasks=SimpleNamespace(BaseOptions=Mock(), vision=SimpleNamespace(
                PoseLandmarkerOptions=self.options, RunningMode=SimpleNamespace(VIDEO='video'),
                PoseLandmarker=SimpleNamespace(create_from_options=Mock(return_value=self.task)))),
            Image=Mock(return_value='image'), ImageFormat=SimpleNamespace(SRGB='srgb'),
        )
        self.frame = SimpleNamespace(shape=(720, 1280, 3))

    def adapter(self):
        return MediaPipePose(self.model, min_visibility=.5, mp_module=self.mp, cv2_module=self.cv)

    def test_task_reused_video_mode_and_milliseconds_do_not_change_engine_seconds(self):
        with self.adapter() as pose:
            a = pose.process(self.frame, .0001)
            b = pose.process(self.frame, .0002)
            self.assertEqual((a.measurement.timestamp, b.measurement.timestamp), (.0001, .0002))
        self.assertEqual([c.args[1] for c in self.task.detect_for_video.call_args_list], [0, 1])
        self.options.assert_called_once()
        self.assertEqual(self.options.call_args.kwargs['running_mode'], 'video')
        self.task.close.assert_called_once()

    def test_missing_model_error_is_actionable(self):
        with self.assertRaisesRegex(PoseError, 'download-model'):
            with MediaPipePose(self.model.parent / 'missing.task', min_visibility=.5):
                pass

    def test_no_pose_is_not_inference_failure(self):
        self.task.detect_for_video.return_value = SimpleNamespace(pose_landmarks=[])
        with self.adapter() as pose:
            self.assertFalse(pose.process(self.frame, 0).measurement.person_present)

    def test_inference_failure_is_explicit_and_releases_model(self):
        self.task.detect_for_video.side_effect = RuntimeError('inference failure')
        with self.assertRaisesRegex(PoseError, 'inferencia'):
            with self.adapter() as pose:
                pose.process(self.frame, 0)
        self.task.close.assert_called_once()

    def test_duplicate_pose_timestamp_is_rejected(self):
        with self.adapter() as pose:
            pose.process(self.frame, 1)
            with self.assertRaises(PoseError):
                pose.process(self.frame, 1)


class RunnerTests(unittest.TestCase):
    def test_model_download_is_explicit_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pose.task'
            content = io.BytesIO()
            with zipfile.ZipFile(content, 'w') as archive:
                archive.writestr('model.tflite', b'model fixture')
            with patch('runner.urlopen', return_value=io.BytesIO(content.getvalue())) as network:
                runner.download_model(path)
                self.assertEqual(path.read_bytes(), content.getvalue())
                with self.assertRaises(ValueError):
                    runner.download_model(path)
                network.assert_called_once()

    def test_model_download_failure_leaves_no_partial_model(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pose.task'
            with patch('runner.urlopen', return_value=io.BytesIO(b'invalid response')):
                with self.assertRaises(ValueError):
                    runner.download_model(path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_sources_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit), patch('sys.stderr'):
            runner.parser().parse_args(['--video', 'test.mp4', '--camera', '0'])

    def test_invalid_fps_and_negative_camera_are_rejected(self):
        for args in (['--camera', '-1'], ['--video-fps', '30'],
                     ['--video', 'test.mp4', '--video-fps', 'nan'],
                     ['--recovery-seconds', '0'], ['--cancel-seconds', 'nan'],
                     ['--floor-confirm-seconds', '-1']):
            with self.subTest(args=args), self.assertRaises(SystemExit), patch('sys.stderr'):
                runner.main(args)

    def test_missing_dependencies_produce_actionable_exit(self):
        with patch('runner.run', side_effect=ImportError('cv2')), self.assertLogs('fall_detector') as log:
            self.assertEqual(runner.main([]), 1)
        self.assertIn('requirements.txt', '\n'.join(log.output))

    def test_capture_failure_is_nonzero_and_not_a_successful_end(self):
        with patch('runner.run', side_effect=CaptureError('camera lost')), self.assertLogs('fall_detector'):
            self.assertEqual(runner.main([]), 1)

    def test_diagnostic_text_separates_state_tracking_and_invalid_reason(self):
        result = FallDetector().update(Measurement(0, True, visibility=.1))
        text = '\n'.join(diagnostic_lines(result))
        self.assertIn('INVALID', text)
        self.assertIn('low_visibility', text)
        self.assertIn('velocidad=--', text)

    def test_runtime_composes_source_pose_engine_and_closes_resources(self):
        source = Mock()
        source.is_video = True
        source.fps = 25
        source.timing_warning = None
        source.read.side_effect = [SimpleNamespace(image='frame', timestamp=0), None]
        pose = Mock()
        pose.process.return_value = landmarks_to_measurement(body(), 0, 1280, 720, .5)
        with patch('runner.OpenCVSource') as source_class, patch('runner.MediaPipePose') as pose_class:
            source_class.return_value.__enter__.return_value = source
            pose_class.return_value.__enter__.return_value = pose
            args = runner.parser().parse_args(['--video', 'test.mp4', '--no-preview'])
            self.assertEqual(runner.run(args), 0)
            pose.process.assert_called_once_with('frame', 0)
            source_class.return_value.__exit__.assert_called_once()
            pose_class.return_value.__exit__.assert_called_once()


HAS_RUNTIME = all(importlib.util.find_spec(name) is not None for name in ('cv2', 'mediapipe', 'numpy'))


@unittest.skipUnless(HAS_RUNTIME and runner.DEFAULT_MODEL.is_file(),
                     'Requiere dependencias de requirements.txt y modelo descargado')
class RealAdapterTests(unittest.TestCase):
    def test_preview_renders_skeleton_and_diagnostics_without_opening_a_window(self):
        import cv2
        import numpy as np

        image = np.zeros((240, 320, 3), dtype=np.uint8)
        observation = landmarks_to_measurement(body(), 0, 320, 240, .5)
        result = FallDetector().update(observation.measurement)
        with patch.object(cv2, 'namedWindow'), patch.object(cv2, 'imshow') as display, \
                patch.object(cv2, 'waitKey', return_value=ord('q')) as keyboard, \
                patch.object(cv2, 'getWindowProperty', return_value=1) as visible, \
                patch.object(cv2, 'destroyAllWindows') as destroy:
            with OpenCVPreview(.5) as preview:
                self.assertFalse(preview.show(image, observation, result))
                keyboard.return_value = -1
                visible.side_effect = cv2.error('window already closed')
                self.assertFalse(preview.show(image, observation, result))
            drawn = display.call_args.args[1]
            self.assertEqual(drawn.shape, (450, 960, 3))
            self.assertGreater(np.count_nonzero(drawn[:240]), 0)
            self.assertGreater(np.max(drawn[240:]), 25)
            self.assertEqual(np.count_nonzero(image), 0)
            destroy.assert_called_once()

    def test_real_video_decode_pose_and_engine_on_blank_frames(self):
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'blank.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
            self.assertTrue(writer.isOpened())
            try:
                for _ in range(12):
                    writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
            finally:
                writer.release()
            detector = FallDetector()
            with OpenCVSource(path) as source, MediaPipePose(
                    runner.DEFAULT_MODEL, min_visibility=detector.config.min_visibility) as pose:
                count = 0
                previous = -1
                while (frame := source.read()) is not None:
                    self.assertGreater(frame.timestamp, previous)
                    previous = frame.timestamp
                    result = detector.update(pose.process(frame.image, frame.timestamp).measurement)
                    self.assertEqual(result.tracking, TrackingStatus.ABSENT)
                    count += 1
                self.assertEqual(count, 12)


if __name__ == '__main__':
    unittest.main()
