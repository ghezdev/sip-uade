"""Pixel selection and runner routing, without camera or inference."""

import importlib.util
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adapters.mediapipe_pose import PoseObservation
from fall_detection import Measurement
import runner


class CropArgumentTests(unittest.TestCase):
    def test_default_and_explicit_modes(self):
        self.assertEqual(runner.parser().parse_args([]).crop, 'none')
        for mode in ('left', 'right', 'none'):
            self.assertEqual(runner.parser().parse_args(['--crop', mode]).crop, mode)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(SystemExit), patch('sys.stderr'):
            runner.parser().parse_args(['--crop', 'center'])


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Requiere NumPy para comprobar pixeles')
class CropFrameTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_each_half_preserves_pixels_height_channels_and_dtype(self):
        image = self.np.arange(4 * 8 * 3, dtype=self.np.uint8).reshape(4, 8, 3)
        original = image.copy()
        for mode, expected in (('left', original[:, :4]), ('right', original[:, 4:])):
            with self.subTest(mode=mode):
                cropped = runner.crop_frame(image, mode)
                self.np.testing.assert_array_equal(cropped, expected)
                self.assertEqual(cropped.shape, (4, 4, 3))
                self.assertEqual(cropped.dtype, image.dtype)
                self.assertTrue(cropped.flags.c_contiguous)
                self.assertFalse(self.np.shares_memory(cropped, image))
        self.np.testing.assert_array_equal(image, original)

    def test_none_preserves_full_frame(self):
        image = self.np.zeros((480, 640, 3), dtype=self.np.uint8)
        self.assertIs(runner.crop_frame(image), image)
        self.assertIs(runner.crop_frame(image, 'none'), image)

    def test_odd_width_assigns_center_column_to_right_without_losing_pixels(self):
        image = self.np.arange(3 * 5 * 3).reshape(3, 5, 3)
        left = runner.crop_frame(image, 'left')
        right = runner.crop_frame(image, 'right')
        self.assertEqual(left.shape, (3, 2, 3))
        self.assertEqual(right.shape, (3, 3, 3))
        self.np.testing.assert_array_equal(self.np.concatenate((left, right), axis=1), image)

    def test_invalid_dimensions_or_mode_raise_clear_error(self):
        for shape in ((4, 1, 3), (4, 0, 3), (0, 4, 3), (4,)):
            for mode in ('left', 'right'):
                with self.subTest(shape=shape, mode=mode), self.assertRaises(ValueError):
                    runner.crop_frame(self.np.zeros(shape), mode)
        with self.assertRaises(ValueError):
            runner.crop_frame(self.np.zeros((4, 4, 3)), 'center')

    def test_runner_passes_same_crop_to_pose_and_preview_preserving_video_timestamps(self):
        image = self.np.zeros((6, 10, 3), dtype=self.np.uint8)
        image[:, :5] = 25
        image[:, 5:] = 200
        timestamps = (.125, .375)
        for mode in ('left', 'right', 'none'):
            with self.subTest(mode=mode):
                source = Mock(is_video=True, fps=25, timing_warning=None)
                source.read.side_effect = [SimpleNamespace(image=image, timestamp=t)
                                           for t in timestamps] + [None]
                pose = Mock()
                pose.process.side_effect = lambda img, t: PoseObservation(Measurement(t, False))
                preview = Mock()
                preview.show.return_value = True
                with patch('runner.OpenCVSource') as source_type, \
                        patch('runner.MediaPipePose') as pose_type, \
                        patch('runner.OpenCVPreview') as preview_type, \
                        self.assertLogs('fall_detector'):
                    source_type.return_value.__enter__.return_value = source
                    pose_type.return_value.__enter__.return_value = pose
                    preview_type.return_value.__enter__.return_value = preview
                    args = runner.parser().parse_args(['--video', 'combined.avi', '--crop', mode])
                    self.assertEqual(runner.run(args), 0)
                expected = image if mode == 'none' else image[:, :5] if mode == 'left' else image[:, 5:]
                self.assertEqual(pose.process.call_count, 2)
                self.assertEqual(preview.show.call_count, 2)
                for t, pose_call, preview_call in zip(timestamps, pose.process.call_args_list,
                                                     preview.show.call_args_list):
                    processed_image, timestamp = pose_call.args
                    self.np.testing.assert_array_equal(processed_image, expected)
                    self.assertEqual(timestamp, t)
                    self.assertIs(preview_call.args[0], processed_image)
                    self.assertEqual(preview_call.args[1].measurement.timestamp, t)
                    self.assertEqual(preview_call.args[2].timestamp, t)


if __name__ == '__main__':
    unittest.main()
