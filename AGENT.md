# Fall Detector Project Agent Guide

## Goal

Build a fall detection system for older adults using a camera-based Python detector. The detector is the most important component and must work independently from the web layer.

When a possible fall is detected, the system should wait for a cancellation window. If the alert is not cancelled, it should send a notification through Telegram.

## Current Status

The project has historical material from early tests and the first presentation. These files are useful for context, but they are not the source of truth for the final architecture.

First test material:

- `FirstTests/detector_caidas.py`
- Uses OpenCV, MediaPipe, NumPy, and optional Telegram alerts.
- Detects body posture using pose landmarks.
- Tracks hip descent, fall speed, body aspect ratio, and immobility time.
- Includes a cancellation countdown before sending the alert.
- Sends Telegram messages if token and chat ID are configured.

First presentation material:

- `Presentation1/fallDetectionTestingV1.py`
- `Presentation1/TestLocal1Video.mp4`
- `Presentation1/Una-caida-puede-cambiar-el-dia.pdf`

Rules for agents and future development:

- `FirstTests/` is only the first test that was run.
- `Presentation1/` is only the first presentation material.
- Ignore all files in `Presentation1/` when designing or implementing the final system.
- Do not treat any existing prototype file as the final source of truth.
- Use this `AGENT.md` file as the planning and architecture guide until a real implementation exists.

## Architecture

The project should be separated into four main modules:

1. Detector Engine
2. Camera/Pose Adapters
3. Alert Workflow
4. Web/API Layer

The detector should not depend directly on the web interface or Telegram. The web/API should only consume detector status and events, and the alert workflow should decide when an event becomes a message.

The most important seam is between the detector engine and everything else. The detector engine should accept measurements and return states/events. Camera reading, MediaPipe, Telegram, and FastAPI should sit outside that seam as adapters.

This keeps the detector module deep: most of the fall-detection complexity stays behind a small interface that can be tested without a camera, without Telegram, and without the web server.

The first architecture objective is not to create many files. The first objective is to create one valuable seam: measurement in, detector state and detector events out.

## Detector Engine

Responsibilities:

- Classify the current state as standing, falling, on the floor, recovered, or no person detected.
- Avoid false positives when the person sits, bends down, or briefly disappears from frame.
- Emit events when a fall is detected.

Initial detector states:

- `NO_PERSON`
- `STANDING`
- `FALLING`
- `ON_FLOOR`
- `RECOVERED`

Detector events:

- `person_detected`
- `person_lost`
- `fall_started`
- `person_on_floor`
- `fall_confirmed`
- `person_recovered`

Important parameters:

- `FALL_SPEED_THRESHOLD`
- `MIN_DESCENT`
- `LYING_ASPECT_RATIO`
- `IMMOBILE_SECONDS`
- `MIN_VISIBILITY`

The detector engine should not import OpenCV, MediaPipe, FastAPI, Telegram, or `requests`.

Expected detector engine interface:

```text
update(measurement, timestamp) -> DetectorResult
```

`measurement` should contain normalized body information, not MediaPipe landmarks:

- `person_present`
- `hip_y`
- `torso_length`
- `aspect_ratio`
- `visibility`
- `timestamp`

`DetectorResult` should contain:

- Current detector state.
- New detector events.
- Debug metrics such as fall speed, hip descent, aspect ratio, and time on floor.

This interface is the test surface. Unit tests should be able to feed synthetic measurements into the detector engine without opening a camera or loading MediaPipe.

## Camera/Pose Adapters

Responsibilities:

- Read frames from the camera or test videos.
- Run MediaPipe pose detection.
- Convert landmarks into normalized body measurements.
- Optionally draw the debug preview with OpenCV.

The adapter can use OpenCV and MediaPipe. The detector engine should only receive simple measurement data, such as hip position, torso length, body aspect ratio, visibility, and timestamp.

The first-test `medir()` logic is an example of what belongs in this adapter area because it depends on MediaPipe landmark indexes, landmark visibility, and NumPy calculations.

The adapter seam should support two inputs over time:

- Live webcam frames for the demo.
- Recorded videos or recorded measurements for repeatable testing.

## Alert Workflow

Responsibilities:

- Receive `fall_confirmed` events from the detector engine.
- Start a cancellation countdown.
- Send alert if not cancelled.
- Support Telegram as the first alert channel.
- Log alert status and errors.

Alert states:

- `IDLE`
- `COUNTDOWN`
- `CANCELLED`
- `SENT`
- `FAILED`

Important parameters:

- `CANCEL_SECONDS`

Telegram alert content should include:

- Time of detection.
- Message saying a possible fall was detected.
- How long the person stayed on the floor.
- Optional location/name if configured later.

Secrets should not be hardcoded in the detector code.

Use environment variables:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

## Web/API Layer

The web part should be separate from the detector logic.

Possible responsibilities:

- Show detector status.
- Show latest events.
- Configure thresholds.
- Enable/disable Telegram alerts.
- Trigger test alerts.
- Display camera/detector health.
- Eventually support multiple rooms/cameras.

Suggested backend:

- FastAPI

Possible API endpoints:

- `GET /health`
- `GET /status`
- `GET /events`
- `POST /alerts/test`
- `POST /detector/start`
- `POST /detector/stop`
- `GET /config`
- `PUT /config`

The detector should be able to run without the web server.

The first web version should avoid owning the detector loop. It should read status, expose recent events, and send test alerts. Starting/stopping the detector from the web can be added later if needed.

The web layer should not call MediaPipe directly and should not know how fall classification works. Its leverage comes from observing detector results through the detector interface.

## Suggested Folder Structure

```text
sip-uade/
  AGENT.md
  README.md
  fall_detection/
    __init__.py
    engine.py
    measurements.py
    config.py
  adapters/
    __init__.py
    camera.py
    mediapipe_pose.py
    opencv_preview.py
  alerts/
    __init__.py
    telegram.py
    workflow.py
  runner.py
  web/
    __init__.py
    main.py
    routes.py
  tests/
    test_fall_detector.py
    test_alert_service.py
  FirstTests/
    detector_caidas.py
    evidencia-prompt-claude.md
    Guia rapida de armado.md
  Presentation1/
    fallDetectionTestingV1.py
    TestLocal1Video.mp4
    Una-caida-puede-cambiar-el-dia.pdf
```

## Implementation Phases

## Phase 1: Clean Detector Prototype

Goal: create the first clean detector implementation by extracting the detector engine seam first.

Tasks:

- Move constants into a config object or config file.
- Extract the state machine from `main()` into the detector engine.
- Keep the detector engine interface small: measurement in, state/events/debug metrics out.
- Move `medir()` into a MediaPipe adapter after the engine seam exists.
- Use the first test only as historical context when useful, not as the source of truth.
- Keep OpenCV preview for testing.
- Keep Telegram optional.

Deliverable:

- A cleaner detector that still runs locally with `python runner.py` or an equivalent command.
- Detector engine tests that run without webcam, OpenCV preview, Telegram, or FastAPI.

## Phase 2: Detector Events

Goal: make the detector produce events instead of directly controlling alerts.

Tasks:

- Define detector event types: `person_detected`, `person_lost`, `fall_started`, `person_on_floor`, `fall_confirmed`, and `person_recovered`.
- Create a simple event object.
- Make the detector return or publish events.
- Keep console logging for debugging.

Deliverable:

- Detector can run alone and report fall events.

## Phase 3: Telegram Alert Service

Goal: isolate Telegram from the detector.

Tasks:

- Create an alert workflow that handles countdown, cancellation, sent, and failed states.
- Create a Telegram alert module.
- Read token and chat ID from environment variables.
- Add safe error handling.
- Add a test-alert function.
- Avoid crashing detector if Telegram fails.

The alert workflow should consume detector events. It should not call detector internals, inspect MediaPipe landmarks, or modify detector state.

Deliverable:

- Telegram alerts work independently from detector logic.

## Phase 4: Web/API Backend

Goal: add a web backend that observes detector status and alert history.

Tasks:

- Create a FastAPI app.
- Add health/status endpoints.
- Add test alert endpoint.
- Add detector status endpoint.
- Add event history endpoint.
- Keep start/stop control out of the first web version unless the local runner is stable.
- Decide later whether the detector runs inside the API process or as a separate process.

Deliverable:

- Local web API can show detector status, show recent events, and send test Telegram alerts.

## Phase 5: Configuration

Goal: make the system configurable without editing code.

Tasks:

- Add `.env` support.
- Add threshold configuration.
- Add camera index configuration.
- Add alert timing configuration.
- Add documentation for each setting.

Deliverable:

- Users can configure the system from environment variables or config file.

## Phase 6: Testing and Validation

Goal: prove that the detector works and identify false positives.

Test cases:

- Real fall forward.
- Real fall backward.
- Real fall sideways.
- Sitting quickly.
- Lying down intentionally.
- Bending down.
- Walking toward camera.
- Walking away from camera.
- Person temporarily leaving frame.
- Poor lighting.
- Partial body visible.

Metrics to record:

- True positives.
- False positives.
- False negatives.
- Detection delay.
- Alert delay.
- Telegram success/failure.

Deliverable:

- A table of test results with tuned thresholds.

## Phase 7: Documentation and Demo

Goal: prepare the project for presentation.

Tasks:

- Write README.
- Explain how detection works.
- Explain how Telegram setup works.
- Add installation instructions.
- Add demo steps.
- Add limitations.
- Add future improvements.

Deliverable:

- Project can be understood, installed, and demonstrated.

## Technical Decisions

Initial decisions:

- Use Python for detector.
- Use OpenCV for camera.
- Use MediaPipe for pose detection.
- Use Telegram Bot API for alerts.
- Use FastAPI for future web/API backend.
- Keep detector independent from web and Telegram.
- Keep camera/MediaPipe code in adapters, not inside the detector engine.
- Treat `FirstTests/` as historical first-test material.
- Ignore `Presentation1/` for implementation decisions.

Open decisions:

- Should the web API start/stop the detector, or should the detector run as a separate process?
- Should alert events be stored in a file, SQLite database, or only memory at first?
- Should the camera preview be part of the final version or only for testing?
- Should the final deployment run on a laptop, Raspberry Pi, or another device?

## Architecture Rules

Use these rules while building the first clean implementation:

- Prefer a few deep modules over many shallow modules.
- Preserve locality for threshold tuning: fall speed, hip descent, aspect ratio, and immobility logic should remain easy to read together.
- Extract only around real seams, not around every helper function.
- Use the deletion test before adding a new module.
- If deleting a file only moves the same complexity somewhere else, the module is probably shallow.
- If deleting a file concentrates complexity behind a smaller interface, the module is probably useful.

Deletion tests:

- Delete Telegram: the detector still classifies falls.
- Delete OpenCV preview: the detector still processes measurements.
- Delete the web layer: the detector and alert workflow still run locally.
- Delete the camera adapter: detector tests still run from recorded or synthetic measurements.

Recommended first modules:

- `fall_detection.engine`: deep module for fall state and detector events.
- `adapters.mediapipe_pose`: adapter from MediaPipe landmarks to normalized measurements.
- `alerts.workflow`: countdown, cancellation, sent, and failed alert states.
- `alerts.telegram`: adapter for Telegram Bot API.
- `runner.py`: composition point that connects camera, pose adapter, detector engine, alert workflow, and preview.

## Architecture Review Notes

The first test is useful as historical context, but it is shallow as architecture because one script owns camera access, pose detection, fall classification, alert countdown, Telegram, and UI preview.

The planned architecture should deepen the detector engine module. Its interface should be much smaller than its implementation: normalized measurements go in, detector state and domain events come out.

The highest-leverage refactor is extracting the detector engine before adding FastAPI. That improves testability and keeps the web layer from inheriting the current script's coupling.

The main seams are:

- Camera/Pose adapter seam: lets the detector run with webcam frames now and recorded test videos later.
- Alert adapter seam: lets Telegram be replaced or extended without changing fall detection logic.
- Web/API seam: lets the web layer observe status and events without controlling detection internals.

Avoid creating too many tiny files before the behavior is stable. Start with a small number of deep modules, then split only when a file has a clear reason to change independently.

## Risks

Main risks:

- False positives when someone sits quickly or lies down intentionally.
- False negatives if the person is partially outside the camera frame.
- MediaPipe may fail in poor lighting.
- Camera angle strongly affects detection quality.
- Telegram requires internet connection.
- Hardcoded thresholds may not work in every room.

Mitigations:

- Tune thresholds using recorded test videos.
- Add cancellation countdown.
- Document recommended camera placement.
- Keep logs for debugging.
- Make thresholds configurable.

## Immediate Next Step

Start a clean implementation from this guide. Build the detector engine first, then connect camera/pose adapters and alerts around it.

The first implementation should prioritize detector correctness before building the web layer.
